from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from stage3_support import make_raw_message
from stage5_support import SyntheticM3Transport, pre_m3_message, recovery_context
from stage7_support import (
    canary_context,
    canary_message,
    m3_canary_context,
    m3_canary_message,
    phase_observation,
    protected_m3_context,
)

from moomooau_archive.age_stream import is_age_envelope
from moomooau_archive.canary_runtime import CanaryRuntimeError, M3CanaryRunResult
from moomooau_archive.github_guard import InstallationTokenFailureClass
from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.m3 import (
    ExactMessageTrashExecutor,
    GmailLabelConfirmationClient,
    M3Error,
    MutationBudget,
    MutationPhase,
)
from moomooau_archive.protected_m3 import M3_SECRET_NAMES, ProtectedM3BootstrapError
from moomooau_archive.protected_m3_diagnostics import (
    ProtectedM3AggregateFailureClass,
    ProtectedM3Diagnostics,
    ProtectedM3FailurePhase,
    public_failure_payload,
)
from moomooau_archive.protected_m3_entrypoint import (
    CONTROL_OWNER_ID,
    CONTROL_REF,
    CONTROL_REPOSITORY_ID,
    CONTROL_WORKFLOW_REF,
    M3_CONFIRMATION,
    PROTECTED_ENVIRONMENT,
    ExactM3EnvironmentSecretSource,
    ProtectedM3EntrypointError,
    beta_receipt_sha256,
    execute_protected,
    execution_contract,
    m3_gate_sha256,
)
from moomooau_archive.release_control import (
    FeatureFlags,
    GateStatus,
    ReleaseControlError,
    ReleasePhase,
    Stage7ReleaseGate,
)
from moomooau_archive.remote_recovery_gate import RemoteRecoveryError, RemoteRecoveryGate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]


def test_t0703_m3_canary_requires_budget_one_and_complete_deterministic_evidence() -> None:
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

    same_day = phase_observation(ReleasePhase.M3_CANARY, days=0, scheduled_runs=0)
    same_day_report = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.BLUE_GREEN,
        (alpha, beta, same_day),
        beta_message_budget=1,
        parser_current_version="1.0.0",
    )
    assert same_day_report.status is GateStatus.READY

    wrong_budget = phase_observation(ReleasePhase.M3_CANARY, mutation_budget_max=2)
    no_recovery = phase_observation(
        ReleasePhase.M3_CANARY,
        recovery_successes=0,
    )
    for observation, code in (
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


def test_t0703_reconciles_the_preexisting_trashed_source_with_zero_new_writes() -> None:
    message = m3_canary_message("msg-stage7-m3-unknown-outcome-reconciliation")
    observed = datetime(2026, 7, 24, tzinfo=UTC)
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with m3_canary_context((message,)) as context:
        initial = context.runner.run(
            ReleasePhase.M3_CANARY,
            maximum_verified_candidates=1,
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            observed_at_utc=observed,
            predecessor_observations=predecessors,
            beta_message_budget=1,
        )
        assert initial.confirmed_trashed == initial.mutation_calls == 1
        raw_writes = context.raw_store.create_calls
        processed_writes = context.processed_store.write_calls
        trash_calls = len(context.transport.trashed_ids)

        reconciled = context.runner.run(
            ReleasePhase.M3_CANARY,
            maximum_verified_candidates=1,
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            observed_at_utc=observed,
            predecessor_observations=predecessors,
            beta_message_budget=1,
            reconcile_prior_unknown_mutation=True,
        )

        assert reconciled.reconciliation_mode is True
        assert reconciled.raw_archived == reconciled.full_recovery_successes == 1
        assert reconciled.processed_complete == reconciled.already_trashed == 1
        assert reconciled.mutation_calls == reconciled.confirmed_trashed == 0
        assert context.raw_store.create_calls == raw_writes
        assert context.processed_store.write_calls == processed_writes
        assert len(context.transport.trashed_ids) == trash_calls
        assert reconciled.to_public_dict()["new_mutation_budget_max"] == 0
        assert reconciled.to_public_dict()["reconciled_prior_unknown_mutation_bucket"] == "ONE"
        raw_after_trash = context.transport.send(
            HttpRequest(
                "GET",
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                f"{message.message_id}?format=raw",
            )
        )
        assert raw_after_trash.status == 200
        assert json.loads(raw_after_trash.body)["labelIds"] == [
            "CATEGORY_UPDATES",
            "TRASH",
        ]


def test_t0703_zero_mutation_reconciliation_rejects_no_or_multiple_exact_matches() -> None:
    messages = (
        m3_canary_message("msg-stage7-m3-reconcile-first"),
        m3_canary_message("msg-stage7-m3-reconcile-second"),
    )
    observed = datetime(2026, 7, 24, tzinfo=UTC)
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with m3_canary_context(messages) as context:
        with pytest.raises(CanaryRuntimeError, match="not exactly one"):
            context.runner.run(
                ReleasePhase.M3_CANARY,
                maximum_verified_candidates=1,
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                observed_at_utc=observed,
                predecessor_observations=predecessors,
                beta_message_budget=1,
                reconcile_prior_unknown_mutation=True,
            )
        assert context.raw_store.create_calls == 0
        assert context.processed_store.write_calls == 0
        assert context.transport.trashed_ids == []

        for _ in range(2):
            context.runner.run(
                ReleasePhase.M3_CANARY,
                maximum_verified_candidates=2,
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                observed_at_utc=observed,
                predecessor_observations=predecessors,
                beta_message_budget=1,
            )
        assert set(context.transport.trashed_ids) == {item.message_id for item in messages}
        raw_writes = context.raw_store.create_calls
        processed_writes = context.processed_store.write_calls
        trash_calls = len(context.transport.trashed_ids)
        with pytest.raises(CanaryRuntimeError, match="not exactly one"):
            context.runner.run(
                ReleasePhase.M3_CANARY,
                maximum_verified_candidates=1,
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                observed_at_utc=observed,
                predecessor_observations=predecessors,
                beta_message_budget=1,
                reconcile_prior_unknown_mutation=True,
            )
        assert context.raw_store.create_calls == raw_writes
        assert context.processed_store.write_calls == processed_writes
        assert len(context.transport.trashed_ids) == trash_calls


def test_t0703_m3_runner_quarantines_unverifiable_metadata_then_completes_budget_one() -> None:
    malformed = m3_canary_message("msg-stage7-m3-0-malformed")
    verified = m3_canary_message("msg-stage7-m3-1-verified")
    observed = datetime(2026, 7, 22, tzinfo=UTC)
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    diagnostics = ProtectedM3Diagnostics()
    with m3_canary_context(
        (malformed, verified),
        diagnostics=diagnostics,
        malformed_metadata_ids=frozenset({malformed.message_id}),
    ) as context:
        result = context.runner.run(
            ReleasePhase.M3_CANARY,
            maximum_verified_candidates=1,
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            observed_at_utc=observed,
            predecessor_observations=predecessors,
            beta_message_budget=1,
        )

        assert context.transport.inner.metadata_fetches == [
            malformed.message_id,
            verified.message_id,
            verified.message_id,
        ]
        assert context.transport.inner.raw_fetches == [verified.message_id]
        assert result.metadata_quarantined == 1
        assert result.raw_archived == result.full_recovery_successes == 1
        assert result.processed_complete == result.confirmed_trashed == 1
        assert result.mutation_calls == 1
        assert context.transport.trashed_ids == [verified.message_id]
        assert diagnostics.phase is ProtectedM3FailurePhase.TRASH_MUTATION


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

    diagnostics = ProtectedM3Diagnostics()
    with m3_canary_context(
        (m3_canary_message("msg-stage7-m3-corrupt"),),
        diagnostics=diagnostics,
    ) as context:
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
        assert diagnostics.phase is ProtectedM3FailurePhase.RAW_RECOVERY


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


def test_t0703_protected_m3_bootstrap_recovers_processed_before_exact_trash_and_cleans() -> None:
    message = m3_canary_message("msg-stage7-protected-m3")
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with protected_m3_context((message,)) as context:
        with context.bootstrap.open(predecessor_observations=predecessors) as runtime:
            result = runtime.run()
            assert runtime.closed is True
        assert result.raw_archived == result.full_recovery_successes == 1
        assert result.processed_complete == result.confirmed_trashed == 1
        assert result.mutation_calls == 1
        assert context.gmail_transport.trashed_ids == [message.message_id]
        assert context.github_transport.write_calls > 2
        assert all(is_age_envelope(value) for value in context.github_transport.objects.values())
        assert list(context.tmpfs_root.iterdir()) == []
    assert context.source.all_issued_destroyed


def test_t0703_protected_bootstrap_reconciles_without_gmail_or_repository_write() -> None:
    message = m3_canary_message("msg-stage7-protected-m3-zero-write-reconciliation")
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with protected_m3_context((message,)) as context:
        with context.bootstrap.open(predecessor_observations=predecessors) as runtime:
            initial = runtime.run()
        assert initial.confirmed_trashed == initial.mutation_calls == 1
        repository_writes = context.github_transport.write_calls
        trash_calls = len(context.gmail_transport.trashed_ids)

        with context.bootstrap.open(
            predecessor_observations=predecessors,
            reconcile_prior_unknown_mutation=True,
        ) as runtime:
            reconciled = runtime.run()

        assert reconciled.reconciliation_mode is True
        assert reconciled.already_trashed == 1
        assert reconciled.mutation_calls == reconciled.confirmed_trashed == 0
        assert context.github_transport.write_calls == repository_writes
        assert len(context.gmail_transport.trashed_ids) == trash_calls
        assert list(context.tmpfs_root.iterdir()) == []
    assert context.source.all_issued_destroyed


def test_t0703_empty_protected_processing_registries_force_recoverable_safe_deferred() -> None:
    message = m3_canary_message("msg-stage7-protected-m3-empty-registry")
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with protected_m3_context(
        (message,),
        empty_processing_registries=True,
    ) as context:
        with context.bootstrap.open(predecessor_observations=predecessors) as runtime:
            result = runtime.run()
        assert result.raw_archived == result.full_recovery_successes == 1
        assert result.processed_complete == 0
        assert result.processed_safe_deferred == result.confirmed_trashed == 1
        assert result.mutation_calls == 1
        assert context.gmail_transport.trashed_ids == [message.message_id]
        assert all(is_age_envelope(value) for value in context.github_transport.objects.values())
        assert list(context.tmpfs_root.iterdir()) == []
    assert context.source.all_issued_destroyed


def test_t0703_empty_protected_registries_safe_defer_quarantined_attachment() -> None:
    message = m3_canary_message(
        "msg-stage7-protected-m3-empty-registry-quarantined",
        with_supported_attachment=False,
    )
    message = replace(
        message,
        raw=make_raw_message(
            message_id=message.message_id,
            subject="Synthetic Moomoo AU Daily DAILY_STATEMENT",
            attachments=(
                (
                    "active.pdf",
                    "application",
                    "pdf",
                    b"%PDF-1.7\n/OpenAction /JavaScript /Launch\n%%EOF\n",
                ),
            ),
        ),
    )
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with protected_m3_context(
        (message,),
        empty_processing_registries=True,
    ) as context:
        with context.bootstrap.open(predecessor_observations=predecessors) as runtime:
            result = runtime.run()
        assert result.raw_archived == result.full_recovery_successes == 1
        assert result.processing_blocked == result.processed_complete == 0
        assert result.processed_safe_deferred == result.confirmed_trashed == 1
        assert result.mutation_calls == 1
        assert context.gmail_transport.trashed_ids == [message.message_id]
        assert all(is_age_envelope(value) for value in context.github_transport.objects.values())
        assert list(context.tmpfs_root.iterdir()) == []
    assert context.source.all_issued_destroyed


def _protected_m3_environment(*, head_sha: str = "b" * 40) -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY_ID": str(CONTROL_REPOSITORY_ID),
        "GITHUB_REPOSITORY_OWNER_ID": str(CONTROL_OWNER_ID),
        "GITHUB_ACTOR_ID": str(CONTROL_OWNER_ID),
        "GITHUB_RUN_ID": "7003001",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": head_sha,
        "GITHUB_REF": CONTROL_REF,
        "GITHUB_WORKFLOW_REF": CONTROL_WORKFLOW_REF,
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MOOMOOAU_PROTECTED_ENVIRONMENT": PROTECTED_ENVIRONMENT,
    }


def _authorized_project_root(tmp_path: Path) -> Path:
    contract = execution_contract(PROJECT_ROOT)
    paths = {
        Path("pyproject.toml"),
        *(Path(item) for item in contract["m3_gate_paths"]),
    }
    for relative in paths:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative, destination)
    run_contract_path = tmp_path / "machine/stages/S7/contracts/run_contract.json"
    run_contract = json.loads(run_contract_path.read_text(encoding="utf-8"))
    run_contract["authorization"] = {
        "purpose": "T0703_PROTECTED_M3_REPAIR_ONLY",
        "m3_authorized": True,
        "final_publication_authorized": False,
        "prior_failed_attempts_exact": 6,
        "zero_mutation_reconciliation_dispatch_limit": 1,
    }
    run_contract["authorized_effect_budget"] = {
        "beta_message_budget": 1,
        "m3_runs_maximum": 1,
        "gmail_mutations_maximum": 0,
        "m3_source_mutation_budget_per_run": 0,
        "verified_full_raw_message_reads_maximum": 1,
        "raw_ciphertext_creations_maximum": 0,
        "processed_writes_maximum": 0,
        "protected_m3_dispatches_maximum": 1,
        "protected_m3_reruns_maximum": 0,
        "prior_protected_m3_dispatches_exact": 6,
        "cumulative_protected_m3_dispatches_after_success_maximum": 7,
        "timeline_writes_maximum": 0,
        "scheduled_runs_maximum": 0,
    }
    run_contract_path.write_text(
        json.dumps(run_contract, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return tmp_path


class _SyntheticProtectedM3Runtime:
    def __init__(self, result: M3CanaryRunResult | None = None) -> None:
        self._result = result

    def run(self) -> M3CanaryRunResult:
        return self._result or M3CanaryRunResult(
            phase=ReleasePhase.M3_CANARY,
            discovered_refs=17,
            metadata_reads=18,
            metadata_quarantined=1,
            verified_candidates=12,
            raw_archived=1,
            processed_complete=1,
            processed_safe_deferred=0,
            processing_blocked=0,
            full_recovery_successes=1,
            mutation_calls=0,
            confirmed_trashed=0,
            already_trashed=1,
            failed_mutation_outcomes=0,
            deferred_mutations=0,
            halted_fail_closed=False,
            reconciliation_mode=True,
        )


class _SyntheticProtectedM3Bootstrap:
    def __init__(self, result: M3CanaryRunResult | None = None) -> None:
        self.predecessors: tuple[object, ...] = ()
        self._result = result

    @contextmanager
    def open(
        self,
        *,
        predecessor_observations: tuple[object, ...],
        reconcile_prior_unknown_mutation: bool = False,
    ) -> Iterator[_SyntheticProtectedM3Runtime]:
        assert reconcile_prior_unknown_mutation is True
        self.predecessors = predecessor_observations
        yield _SyntheticProtectedM3Runtime(self._result)


def test_t0703_protected_entrypoint_contract_is_authorized_and_receipt_bound() -> None:
    contract = execution_contract(PROJECT_ROOT)
    assert contract["mode"] == "CONTRACT_ONLY"
    assert contract["m3_authorized"] is True
    assert contract["required_actor_id"] == CONTROL_OWNER_ID
    assert contract["required_ref"] == CONTROL_REF
    assert contract["required_workflow_ref"] == CONTROL_WORKFLOW_REF
    assert contract["protected_environment"] == "moomooau-beta"
    assert contract["required_runner_environment"] == "github-hosted"
    assert contract["required_run_attempt"] == 1
    assert contract["required_confirmation"] == M3_CONFIRMATION
    assert contract["required_protected_input_count"] == len(M3_SECRET_NAMES) == 8
    assert contract["protected_input_values_disclosed"] is False
    assert "required_secret_names" not in contract
    assert contract["beta_receipt_sha256"] == beta_receipt_sha256(PROJECT_ROOT)
    assert contract["prior_attempt_ledger_path"].endswith("t0703/attempt-ledger.json")
    assert contract["prior_failed_attempts"] == 6
    assert contract["same_head_rerun_allowed"] is False
    assert contract["m3_gate_sha256"] == m3_gate_sha256(PROJECT_ROOT)
    assert contract["feature_invariants"] == {
        "processing_enabled": True,
        "m3_enabled": True,
        "timeline_enabled": False,
        "release_mutation_budget_ceiling": 1,
        "reconciliation_new_mutation_budget": 0,
        "parser_current_version_required": True,
        "empty_protected_registries_force_safe_deferred": True,
    }
    assert contract["maximum_verified_candidates"] == 1
    assert contract["maximum_source_mutations"] == 0
    assert contract["maximum_cumulative_source_mutations"] == 1
    assert contract["maximum_timeline_mutations"] == 0
    assert contract["fixed_calendar_wait_days"] == 0
    assert contract["real_gmail_calls"] == 0
    assert contract["private_repository_calls"] == 0
    assert contract["protected_oracles_executed"] == 0
    assert contract["production_health_claimed"] is False


def test_t0703_secret_source_remains_exact_allowlist() -> None:
    source = ExactM3EnvironmentSecretSource({})
    with pytest.raises(ProtectedM3EntrypointError, match="unavailable"):
        source.read(M3_SECRET_NAMES[0])
    with pytest.raises(ProtectedM3EntrypointError, match="not allowlisted"):
        source.read("MOOMOOAU_NOT_ALLOWLISTED")


def test_t0703_failure_diagnostics_are_closed_public_safe_phases() -> None:
    diagnostics = ProtectedM3Diagnostics()
    for phase in ProtectedM3FailurePhase:
        diagnostics.enter(phase)
        payload = public_failure_payload(diagnostics)
        assert payload == {
            "schema_version": "moomooau.protected-m3-execution.v1",
            "status": "BLOCKED",
            "reason_code": f"PROTECTED_M3_{phase.value}_FAILED",
            "failure_phase": phase.value,
            "installation_token_failure_class": "UNCLASSIFIED",
            "aggregate_failure_class": "UNCLASSIFIED",
            "diagnostic_taxonomy": "moomooau.protected-m3-failure-taxonomy.v1",
            "exact_root_cause_claimed": False,
            "production_health_claimed": False,
            "final_acceptance_claimed": False,
        }
        assert not any(
            token in json.dumps(payload, sort_keys=True).casefold()
            for token in ("message_id", "thread_id", "sender", "subject", "repository_id")
        )

    diagnostics.enter_installation_token_failure(InstallationTokenFailureClass.INSTALLATION_ZERO)
    token_failure = public_failure_payload(diagnostics)
    assert token_failure["failure_phase"] == "GITHUB_APP_TOKEN"
    assert token_failure["installation_token_failure_class"] == "INSTALLATION_ZERO"
    assert token_failure["aggregate_failure_class"] == "UNCLASSIFIED"

    diagnostics.enter_aggregate_failure(ProtectedM3AggregateFailureClass.PROCESSING_BLOCKED)
    aggregate_failure = public_failure_payload(diagnostics)
    assert aggregate_failure["failure_phase"] == "AGGREGATE_GATE"
    assert aggregate_failure["installation_token_failure_class"] == "UNCLASSIFIED"
    assert aggregate_failure["aggregate_failure_class"] == "PROCESSING_BLOCKED"


def test_t0703_bootstrap_preserves_closed_installation_token_failure_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = ProtectedM3Diagnostics()
    message = m3_canary_message("msg-stage7-protected-m3-app-not-installed")
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with protected_m3_context((message,), diagnostics=diagnostics) as context:
        original_send = context.github_transport.send

        def installation_absent(request: object) -> HttpResponse:
            url = getattr(request, "url", "")
            method = getattr(request, "method", "")
            if method == "POST" and "/app/installations/" in url:
                return HttpResponse(404, b"{}")
            if method == "GET" and url.endswith("/app/installations?per_page=2"):
                return HttpResponse(200, b"[]")
            return original_send(request)  # type: ignore[arg-type]

        monkeypatch.setattr(context.github_transport, "send", installation_absent)
        with pytest.raises(
            ProtectedM3BootstrapError,
            match="GitHub App installation token is unavailable",
        ):
            with context.bootstrap.open(predecessor_observations=predecessors):
                pytest.fail("installation-token failure yielded a protected runtime")

    payload = public_failure_payload(diagnostics)
    assert payload["failure_phase"] == "GITHUB_APP_TOKEN"
    assert payload["installation_token_failure_class"] == "INSTALLATION_ZERO"
    assert "repository" not in json.dumps(payload, sort_keys=True).casefold()


def test_t0703_authorized_entrypoint_emits_aggregate_only_evidence(tmp_path: Path) -> None:
    project_root = _authorized_project_root(tmp_path)
    environment = _protected_m3_environment()
    bootstrap = _SyntheticProtectedM3Bootstrap()
    now = datetime(2026, 7, 24, 1, tzinfo=UTC)
    evidence = execute_protected(
        environment,
        project_root=project_root,
        expected_head_sha=environment["GITHUB_SHA"],
        supplied_beta_receipt_sha256=beta_receipt_sha256(project_root),
        supplied_m3_gate_sha256=m3_gate_sha256(project_root),
        confirmation=M3_CONFIRMATION,
        bootstrap=bootstrap,  # type: ignore[arg-type]
        clock=lambda: now,
    )
    rendered = evidence.to_dict()
    assert len(bootstrap.predecessors) == 2
    assert rendered["status"] == "PROTECTED_M3_ZERO_MUTATION_RECONCILIATION_COMPLETED_NOT_FINAL"
    assert rendered["m3_gate_status"] == "PASS"
    assert rendered["phase_observation"] == {
        "phase": "M3_CANARY",
        "provenance": "PROTECTED_GITHUB_ACTIONS",
        "started_at_utc": "2026-07-24T01:00:00Z",
        "ended_at_utc": "2026-07-24T01:00:00Z",
        "observed_runs": 2,
        "processed_or_safe_deferred_present": True,
        "source_mutation_budget": 1,
        "source_mutation_confirmed": True,
        "current_run_source_mutation_budget": 0,
        "prior_unknown_mutation_reconciled": True,
        "remote_recovery_one_hundred_percent": True,
        "collateral_mutations": 0,
        "timeline_publish_attempts": 0,
        "maximum_live_timeline_assets": 0,
        "unresolved_failures": 0,
        "exact_mailbox_counts_disclosed": False,
    }
    assert rendered["public_result"]["verified_bucket"] == "TEN_PLUS"
    assert rendered["public_result"]["confirmed_trashed_bucket"] == "ZERO"
    assert rendered["public_result"]["reconciled_prior_unknown_mutation_bucket"] == "ONE"
    assert rendered["public_result"]["new_mutation_budget_max"] == 0
    assert rendered["boundaries"] == {
        "maximum_verified_candidates": 1,
        "maximum_current_run_source_mutations": 0,
        "maximum_cumulative_source_mutations": 1,
        "timeline_enabled": False,
        "blue_green_enabled": False,
        "schedule_enabled": False,
    }
    assert rendered["production_health_claimed"] is False
    assert rendered["final_acceptance_claimed"] is False
    public_text = json.dumps(rendered, sort_keys=True)
    for forbidden in (
        '"message_id":',
        '"thread_id":',
        '"sender":',
        '"subject":',
        '"attachment":',
        '"private_repository_id":',
    ):
        assert forbidden not in public_text.casefold()


def test_t0703_authorized_entrypoint_classifies_processing_blocked_aggregate(
    tmp_path: Path,
) -> None:
    project_root = _authorized_project_root(tmp_path)
    environment = _protected_m3_environment()
    diagnostics = ProtectedM3Diagnostics()
    result = M3CanaryRunResult(
        phase=ReleasePhase.M3_CANARY,
        discovered_refs=1,
        metadata_reads=1,
        metadata_quarantined=0,
        verified_candidates=1,
        raw_archived=1,
        processed_complete=0,
        processed_safe_deferred=0,
        processing_blocked=1,
        full_recovery_successes=0,
        mutation_calls=0,
        confirmed_trashed=0,
        already_trashed=0,
        failed_mutation_outcomes=0,
        deferred_mutations=0,
        halted_fail_closed=False,
    )
    with pytest.raises(ProtectedM3EntrypointError, match="not evidence-complete"):
        execute_protected(
            environment,
            project_root=project_root,
            expected_head_sha=environment["GITHUB_SHA"],
            supplied_beta_receipt_sha256=beta_receipt_sha256(project_root),
            supplied_m3_gate_sha256=m3_gate_sha256(project_root),
            confirmation=M3_CONFIRMATION,
            bootstrap=_SyntheticProtectedM3Bootstrap(result),  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 7, 24, 1, tzinfo=UTC),
            diagnostics=diagnostics,
        )

    payload = public_failure_payload(diagnostics)
    assert payload["failure_phase"] == "AGGREGATE_GATE"
    assert payload["aggregate_failure_class"] == "PROCESSING_BLOCKED"
    assert payload["exact_root_cause_claimed"] is False
    assert not any(
        token in json.dumps(payload, sort_keys=True).casefold()
        for token in ("message_id", "thread_id", "sender", "subject", "repository_id")
    )


def test_t0703_protected_workflow_is_manual_main_only_authorized_and_exact_eight_secret() -> None:
    path = REPOSITORY_ROOT / ".github/workflows/moomooau-m3.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert workflow["on"].keys() == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "moomooau-m3-zero-mutation-reconciliation",
        "cancel-in-progress": "false",
    }
    gate = workflow["jobs"]["m3-authority-gate"]
    execution = workflow["jobs"]["m3-reconcile-zero-mutation"]
    assert execution["needs"] == "m3-authority-gate"
    assert execution["environment"] == "moomooau-beta"
    assert gate["steps"][0]["name"] == "Fail closed on invalid protected M3 dispatch context"
    assert 'test "$GITHUB_ACTOR_ID" = "68840188"' in gate["steps"][0]["run"]
    assert 'test "$GITHUB_RUN_ATTEMPT" = "1"' in gate["steps"][0]["run"]
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in gate["steps"][0]["run"]
    assert 'test "$EXPECTED_HEAD_SHA" = "$GITHUB_SHA"' in gate["steps"][0]["run"]
    assert M3_CONFIRMATION in gate["steps"][0]["run"]
    assert 'assert value["m3_authorized"] is True' in text
    assert "if" not in gate
    assert "if" not in execution
    secret_names = re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", text)
    assert len(secret_names) == 8
    assert set(secret_names) == set(M3_SECRET_NAMES)
    assert text.count("python -m moomooau_archive.protected_m3_entrypoint") == 2
    assert "--contract-only" in text
    assert "--execute-protected" in text
    assert "tests/tasks/test_t0702.py tests/tasks/test_t0703.py" in text
    assert "src/moomooau_archive/m3.py" in text
    age_archive_sha256 = "bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377"
    assert text.count(age_archive_sha256) == 2
    assert "refs/heads/main" in text
    assert "moomooau-protected-m3-*" in text
    for forbidden in (
        "schedule:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "moomooau_archive.production",
        "moomooau_archive.blue_green_runtime",
    ):
        assert forbidden not in text.casefold()
