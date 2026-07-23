from __future__ import annotations

import pytest
from stage5_support import (
    Stage5RecoveryContext,
    SyntheticM3Transport,
    pre_m3_message,
    recovery_context,
)

from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.m3 import (
    ExactMessageTrashExecutor,
    GmailLabelConfirmationClient,
    M3Error,
    M3State,
    MutationBudget,
    MutationPhase,
)
from moomooau_archive.remote_recovery_gate import MessageRecoveryProof, RemoteRecoveryGate


def _proof(context: Stage5RecoveryContext) -> MessageRecoveryProof:
    return RemoteRecoveryGate(context.reader, context.decryptor).verify(
        context.canonical,
        context.first_verification,
        context.raw_plan,
        context.processed_bundle,
        context.processed_plan,
    )


def test_t0502_canary_calls_only_exact_message_trash_once_then_confirms_label() -> None:
    with recovery_context() as context:
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
            _proof(context),
            MutationBudget.for_phase(MutationPhase.CANARY),
        )
        assert result.state is M3State.TRASHED
        assert result.trash_confirmed
        assert [request.method for request in transport.requests] == ["POST", "GET"]
        assert transport.requests[0].url.endswith(f"/messages/{message.ref.message_id}/trash")
        assert all("threads" not in request.url for request in transport.requests)


def test_t0502_already_in_trash_is_idempotent_and_consumes_no_budget() -> None:
    with recovery_context() as context:
        message, second = pre_m3_message(context, trashed=True)
        transport = SyntheticM3Transport(message.ref.message_id)
        guard = GmailEndpointGuard(transport)
        budget = MutationBudget.for_phase(MutationPhase.CANARY)
        result = ExactMessageTrashExecutor(
            guard,
            GmailLabelConfirmationClient(guard),
        ).execute(message, context.first_verification, second, _proof(context), budget)
        assert result.state is M3State.ALREADY_TRASHED
        assert result.mutation_calls == 0
        assert budget.consumed_calls == 0
        assert transport.requests == []


def test_t0502_alpha_beta_zero_budget_and_failed_second_verification_block_network() -> None:
    with recovery_context() as context:
        message, second = pre_m3_message(context)
        transport = SyntheticM3Transport(message.ref.message_id)
        guard = GmailEndpointGuard(transport)
        executor = ExactMessageTrashExecutor(guard, GmailLabelConfirmationClient(guard))
        with pytest.raises(M3Error, match="exhausted"):
            executor.execute(
                message,
                context.first_verification,
                second,
                _proof(context),
                MutationBudget.for_phase(MutationPhase.ALPHA),
            )
        bad_message, bad_second = pre_m3_message(context, subject="Not a protected fingerprint")
        with pytest.raises(M3Error, match="not bound"):
            executor.execute(
                bad_message,
                context.first_verification,
                bad_second,
                _proof(context),
                MutationBudget.for_phase(MutationPhase.CANARY),
            )
        assert transport.requests == []


def test_t0502_uncertain_response_does_not_retry_inside_the_attempt() -> None:
    with recovery_context() as context:
        message, second = pre_m3_message(context)
        transport = SyntheticM3Transport(message.ref.message_id, trash_status=503)
        guard = GmailEndpointGuard(transport)
        result = ExactMessageTrashExecutor(
            guard,
            GmailLabelConfirmationClient(guard),
        ).execute(
            message,
            context.first_verification,
            second,
            _proof(context),
            MutationBudget.for_phase(MutationPhase.CANARY),
        )
        assert result.state is M3State.UNKNOWN
        assert result.mutation_calls == 1
        assert len(transport.requests) == 1
