from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from stage7_support import (
    ga_context,
    m3_canary_message,
    observations_through,
    phase_observation,
)

from moomooau_archive.adapters import AGE_HEADER
from moomooau_archive.ga_runtime import GARuntimeError
from moomooau_archive.github_guard import (
    CONTENT_GMAIL_SYNC_STATE_MESSAGE,
    GMAIL_SYNC_STATE_PATH,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    InstallationToken,
    RepositoryLocator,
    TargetRepositoryConfig,
    content_url,
)
from moomooau_archive.gmail_discovery import MessageRef, SyncState
from moomooau_archive.gmail_sync_checkpoint import (
    GitHubGmailSyncStateStore,
    GmailRunCheckpoint,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.release_control import GateStatus, ReleasePhase, Stage7ReleaseGate
from moomooau_archive.run_schedule import RunPlanner, RunTrigger, ScheduledRunPlan
from moomooau_archive.secret_values import SecretText
from moomooau_archive.timeline_publish import TimelinePublishAction


class _GitHubSyncTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []
        self.ciphertext: bytes | None = None
        self.revision = "a" * 40

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if request.method == "PUT":
            payload = json.loads(request.body or b"{}")
            self.ciphertext = base64.b64decode(payload["content"], validate=True)
            return HttpResponse(201, b"{}")
        if self.ciphertext is None:
            return HttpResponse(404, b"{}")
        return HttpResponse(
            200,
            json.dumps(
                {
                    "content": base64.b64encode(self.ciphertext).decode("ascii"),
                    "encoding": "base64",
                    "sha": self.revision,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        )


def _synthetic_age_envelope() -> bytes:
    encoded_32_bytes = b"A" * 43
    return b"\n".join(
        (
            AGE_HEADER,
            b"-> X25519 " + encoded_32_bytes,
            encoded_32_bytes,
            b"--- " + encoded_32_bytes,
            b"\x00" * 32,
        )
    )


def _sunday_plan() -> ScheduledRunPlan:
    return RunPlanner().plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 7, 25, 18, 30, tzinfo=UTC),
        last_successful_run_date_sydney=date(2026, 7, 25),
    )


def _monday_plan() -> ScheduledRunPlan:
    return RunPlanner().plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 7, 26, 18, 30, tzinfo=UTC),
        last_successful_run_date_sydney=date(2026, 7, 26),
    )


def _tuesday_plan() -> ScheduledRunPlan:
    return RunPlanner().plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 7, 27, 18, 30, tzinfo=UTC),
        last_successful_run_date_sydney=date(2026, 7, 27),
    )


def test_t0705_ga_needs_real_0430_observation_and_explicit_budget() -> None:
    through_blue_green = observations_through(ReleasePhase.BLUE_GREEN)
    gate = Stage7ReleaseGate()
    missing = gate.evaluate_stage_completion(
        through_blue_green,
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert missing.status is GateStatus.BLOCKED
    assert "GA_PROTECTED_OBSERVATION_MISSING" in missing.reasons

    complete = gate.evaluate_stage_completion(
        observations_through(ReleasePhase.GA),
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert complete.status is GateStatus.READY

    no_budget = gate.evaluate_stage_completion(
        observations_through(ReleasePhase.GA),
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=None,
        ga_capacity_authorized=False,
    )
    assert no_budget.status is GateStatus.BLOCKED
    assert "TARGET_FEATURE_CONFIGURATION_INCOMPLETE" in no_budget.reasons
    assert "GA_CAPACITY_AUTHORIZATION_MISSING" in no_budget.reasons

    no_full_pipeline = observations_through(ReleasePhase.BLUE_GREEN) + (
        phase_observation(
            ReleasePhase.GA,
            source_mutations=0,
            recovery_attempts=0,
            recovery_successes=0,
            processed_messages=0,
            timeline_publish_attempts=0,
            full_reconcile_runs=0,
        ),
    )
    incomplete = gate.evaluate_stage_completion(
        no_full_pipeline,
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert set(incomplete.reasons) >= {
        "GA_NO_PROCESSED_MESSAGE_OBSERVED",
        "GA_NO_TIMELINE_PUBLISH_OBSERVED",
        "GA_FULL_RECONCILIATION_NOT_OBSERVED",
    }


def test_t0705_schedule_plan_is_sydney_0430_and_never_claims_platform_sla() -> None:
    plan = RunPlanner().plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 7, 19, 18, 30, tzinfo=UTC),
        last_successful_run_date_sydney=date(2026, 7, 19),
    )
    public = plan.to_public_dict()
    assert public["target_time"] == "04:30"
    assert public["timezone"] == "Australia/Sydney"
    assert public["platform_sla_claimed"] is False


def test_t0705_github_checkpoint_store_uses_one_encrypted_strict_cas_path() -> None:
    config = TargetRepositoryConfig(repository_id=7_700_005, installation_id=8_700_005)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-private")
    transport = _GitHubSyncTransport()
    guard = GitHubEndpointGuard(transport, config)
    guard.bind_repository(locator)
    token = InstallationToken(
        SecretText("synthetic-" + "ga-checkpoint-token"),
        datetime(2026, 7, 26, tzinfo=UTC) + timedelta(minutes=30),
    )
    store = GitHubGmailSyncStateStore(guard, locator, token)
    ciphertext = _synthetic_age_envelope()
    try:
        committed = store.compare_and_swap(None, ciphertext)
        assert committed.ciphertext == ciphertext
        assert committed.revision == transport.revision
        assert [request.method for request in transport.requests] == ["PUT", "GET"]
        assert all(
            request.url == content_url(locator, GMAIL_SYNC_STATE_PATH)
            for request in transport.requests
        )
        payload = json.loads(transport.requests[0].body or b"{}")
        assert payload["message"] == CONTENT_GMAIL_SYNC_STATE_MESSAGE
        assert "sha" not in payload

        before = len(transport.requests)
        invalid = dict(payload)
        invalid["message"] = "moomooau: append encrypted object"
        with pytest.raises(GitHubBoundaryError, match="Gmail sync state"):
            guard.send(
                HttpRequest(
                    "PUT",
                    content_url(locator, GMAIL_SYNC_STATE_PATH),
                    body=json.dumps(
                        invalid,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode(),
                )
            )
        assert len(transport.requests) == before
    finally:
        token.destroy()


def test_t0705_ga_full_pipeline_audits_reconcile_recovers_then_trashes_and_keeps_one_timeline() -> (
    None
):
    first_id = "msg-stage7-ga-first"
    second_id = "msg-stage7-ga-second"
    messages = (
        m3_canary_message(first_id),
        m3_canary_message(second_id),
    )
    initial = SyncState(
        "9000",
        (MessageRef(first_id, "thread-" + first_id),),
    )
    history_pages: tuple[dict[str, object], ...] = (
        {
            "history": [
                {
                    "id": "9101",
                    "messagesAdded": [
                        {
                            "message": {
                                "id": second_id,
                                "threadId": "thread-" + second_id,
                            }
                        }
                    ],
                }
            ],
            "historyId": "9101",
        },
    )
    predecessors = observations_through(ReleasePhase.BLUE_GREEN)
    with ga_context(
        messages,
        initial_sync_state=initial,
        history_pages=history_pages,
    ) as context:
        first = context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=predecessors,
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )
        result = first.result
        assert result.full_reconcile_runs == result.full_reconcile_comparisons == 1
        assert result.full_reconcile_difference == 0
        assert result.verified_candidates == result.raw_archived == 2
        assert result.processed_complete == result.full_recovery_successes == 2
        assert result.mutation_calls == result.confirmed_trashed == 1
        assert result.deferred_mutations == 1
        assert result.pending_verified_refs == 1
        assert result.timeline_publish_attempts == result.final_live_timeline_assets == 1
        assert result.sync_checkpoint_mutations == result.sync_checkpoint_recoveries == 1
        assert len(first.timeline_snapshot.facts) == 2
        assert len(context.transport.trashed_ids) == 1
        assert context.events.index("recover") < context.events.index("trash")
        assert context.timeline_remote.maximum_observed_asset_count == 1
        checkpoint_ciphertext = context.checkpoint_store.ciphertext()
        assert checkpoint_ciphertext is not None
        assert first_id.encode() not in checkpoint_ciphertext
        assert second_id.encode() not in checkpoint_ciphertext
        public = result.to_public_dict()
        assert public["full_reconcile_comparison"] == "ZERO_DIFFERENCE"
        assert public["production_health_claimed"] is False
        assert "verified_candidates" not in public and "confirmed_trashed" not in public

        second = context.runner.run(
            _monday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=predecessors,
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )
        assert second.result.candidate_refs == 1
        assert second.result.full_reconcile_runs == 0
        assert second.result.already_trashed == 0
        assert second.result.confirmed_trashed == second.result.mutation_calls == 1
        assert second.result.deferred_mutations == 0
        assert second.result.pending_verified_refs == 0
        assert second.result.to_public_dict()["full_reconcile_comparison"] == "NOT_RUN"
        assert len(context.transport.trashed_ids) == 2
        writes_after_backlog = (
            context.raw_store.create_calls,
            context.processed_store.write_calls,
        )

        third = context.runner.run(
            _tuesday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=predecessors,
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )
        assert third.result.candidate_refs == third.result.already_trashed == 0
        assert third.result.mutation_calls == third.result.confirmed_trashed == 0
        assert third.result.pending_verified_refs == 0
        assert third.result.timeline_action is TimelinePublishAction.NO_CHANGE
        # The mailbox truth is unchanged, but the encrypted remote scheduling watermark
        # advances once for the new Sydney run date.
        assert third.result.sync_checkpoint_mutations == 1
        assert (
            context.raw_store.create_calls,
            context.processed_store.write_calls,
        ) == writes_after_backlog
        assert len(context.transport.trashed_ids) == 2
        assert context.timeline_remote.maximum_observed_asset_count == 1


def test_t0705_ga_fails_before_remote_calls_without_protected_predecessors_or_budget() -> None:
    message = m3_canary_message("msg-stage7-ga-gated")
    with ga_context((message,)) as context:
        with pytest.raises(GARuntimeError, match="predecessor"):
            context.runner.run(
                _sunday_plan(),
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                predecessor_observations=observations_through(ReleasePhase.M3_CANARY),
                beta_message_budget=1,
                ga_mutation_budget_per_run=0,
                ga_capacity_authorized=False,
            )
        assert context.transport.inner.requests == []
        assert context.checkpoint_store.read_calls == 0
        assert context.raw_store.create_calls == 0
        assert context.processed_store.write_calls == 0
        assert context.timeline_remote.actions == []


def test_t0705_nonzero_full_reconcile_difference_stops_before_raw_or_mutation() -> None:
    first_id = "msg-stage7-ga-audit-first"
    second_id = "msg-stage7-ga-audit-second"
    initial = SyncState(
        "9000",
        (MessageRef(first_id, "thread-" + first_id),),
    )
    with ga_context(
        (m3_canary_message(first_id), m3_canary_message(second_id)),
        initial_sync_state=initial,
    ) as context:
        with pytest.raises(GARuntimeError, match="differs"):
            context.runner.run(
                _sunday_plan(),
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
                beta_message_budget=1,
                ga_mutation_budget_per_run=1,
                ga_capacity_authorized=True,
            )
        assert context.transport.inner.raw_fetches == []
        assert context.transport.trashed_ids == []
        assert context.raw_store.create_calls == 0
        assert context.processed_store.write_calls == 0
        assert context.timeline_remote.actions == []


def test_t0705_initial_full_reconcile_is_truthfully_not_comparable() -> None:
    with ga_context((m3_canary_message("msg-stage7-ga-initial"),)) as context:
        outcome = context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )
        assert outcome.result.full_reconcile_runs == 1
        assert outcome.result.full_reconcile_comparisons == 0
        assert outcome.result.full_reconcile_difference is None
        assert outcome.result.to_public_dict()["full_reconcile_comparison"] == "NOT_COMPARABLE"


def test_t0705_pending_verified_source_cannot_disappear_from_checkpoint_truth() -> None:
    message_id = "msg-stage7-ga-pending-disappeared"
    ref = MessageRef(message_id, "thread-" + message_id)
    initial = SyncState("9000", (ref,))
    history_pages: tuple[dict[str, object], ...] = (
        {
            "history": [
                {
                    "id": "9101",
                    "messagesDeleted": [
                        {
                            "message": {
                                "id": message_id,
                                "threadId": ref.thread_id,
                            }
                        }
                    ],
                }
            ],
            "historyId": "9101",
        },
    )
    with ga_context(
        (),
        initial_sync_state=initial,
        history_pages=history_pages,
    ) as context:
        recovered = context.checkpoint.recover()
        assert recovered is not None
        context.checkpoint.commit(recovered, GmailRunCheckpoint(initial, (ref,)))

        with pytest.raises(GARuntimeError, match="pending verified source"):
            context.runner.run(
                _monday_plan(),
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
                beta_message_budget=1,
                ga_mutation_budget_per_run=1,
                ga_capacity_authorized=True,
            )

        unchanged = context.checkpoint.recover()
        assert unchanged is not None
        assert unchanged.checkpoint == GmailRunCheckpoint(initial, (ref,))
        assert context.raw_store.create_calls == 0
        assert context.processed_store.write_calls == 0
        assert context.transport.trashed_ids == []
