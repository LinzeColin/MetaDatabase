from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from stage7_support import (
    ga_context,
    m3_canary_message,
    observations_through,
    phase_observation,
)

import moomooau_archive.protected_ga_entrypoint as protected_ga_entrypoint
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
    git_blob_url,
)
from moomooau_archive.gmail_discovery import (
    MessageMetadataUnverifiable,
    MessageRef,
    SyncState,
)
from moomooau_archive.gmail_sync_checkpoint import (
    GitHubGmailSyncStateStore,
    GmailRunCheckpoint,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.processed_commit import (
    GitHubProcessedCiphertextStore,
    ProcessedCommitError,
    RevisionedCiphertext,
)
from moomooau_archive.production import (
    PRODUCTION_CONFIG_SECRET_NAME,
    ProductionBootstrap,
    ProductionExecutionResult,
)
from moomooau_archive.production_adapters import (
    ProductionAdapterError,
    RemoteFirstImportTimestampSource,
)
from moomooau_archive.protected_ga_diagnostics import (
    FAILURE_TAXONOMY_VERSION,
    ProtectedGADiagnostics,
    ProtectedGAFailurePhase,
    public_failure_payload,
)
from moomooau_archive.protected_ga_entrypoint import (
    CONTROL_OWNER_ID,
    CONTROL_REPOSITORY_ID,
    CONTROL_WORKFLOW_REF,
    GA_CONFIRMATION,
    GA_REHEARSAL_CLOCK_UTC,
    DerivedGASecretSource,
    ProtectedGAEntrypointError,
    blue_green_receipt_sha256,
    execute_protected,
    execution_contract,
    ga_gate_sha256,
)
from moomooau_archive.raw_commit import GitHubAppendOnlyCiphertextStore, RawCommitError
from moomooau_archive.release_control import GateStatus, ReleasePhase, Stage7ReleaseGate
from moomooau_archive.run_schedule import RunPlanner, RunTrigger, ScheduledRunPlan
from moomooau_archive.secret_values import SecretText
from moomooau_archive.timeline_publish import TimelinePublishAction

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def _git_blob_revision(payload: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload,
        usedforsecurity=False,
    ).hexdigest()


def test_t0705_raw_recovery_uses_canonical_git_blob_not_contents_media() -> None:
    ciphertext = _synthetic_age_envelope()
    revision = _git_blob_revision(ciphertext)
    raw_path = f"MooMooAU/Raw/messages/2026/07/{'a' * 64}.eml.age"
    config = TargetRepositoryConfig(repository_id=7_500_099, installation_id=8_500_099)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")

    class ContentsMediaMismatchTransport:
        def __init__(self) -> None:
            self.requests: list[HttpRequest] = []

        def send(self, request: HttpRequest) -> HttpResponse:
            self.requests.append(request)
            if request.url == content_url(locator, raw_path):
                assert dict(request.headers)["Accept"] == "application/vnd.github+json"
                return HttpResponse(
                    200,
                    json.dumps(
                        {
                            "content": base64.b64encode(
                                b"contents-inline-representation-differs"
                            ).decode("ascii"),
                            "encoding": "base64",
                            "path": raw_path,
                            "sha": revision,
                            "size": len(ciphertext),
                            "type": "file",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode(),
                )
            assert request.url == git_blob_url(locator, revision)
            assert dict(request.headers)["Accept"] == "application/vnd.github+json"
            encoded = base64.b64encode(ciphertext).decode("ascii")
            wrapped = "\n".join(encoded[index : index + 60] for index in range(0, len(encoded), 60))
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "content": wrapped,
                        "encoding": "base64",
                        "sha": revision,
                        "size": len(ciphertext),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )

    transport = ContentsMediaMismatchTransport()
    guard = GitHubEndpointGuard(transport, config)
    guard.bind_repository(locator)
    token = InstallationToken(
        SecretText("synthetic-installation-token"),
        datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    try:
        recovered = GitHubAppendOnlyCiphertextStore(guard, locator, token).fetch(raw_path)
    finally:
        token.destroy()
    assert recovered == ciphertext
    assert [request.url for request in transport.requests] == [
        content_url(locator, raw_path),
        git_blob_url(locator, revision),
    ]
    assert all(
        dict(request.headers)["Accept"] == "application/vnd.github+json"
        for request in transport.requests
    )


def test_t0705_raw_recovery_fails_closed_on_canonical_blob_revision_drift() -> None:
    metadata_ciphertext = _synthetic_age_envelope()
    returned_ciphertext = metadata_ciphertext[:-1] + b"\x01"
    revision = _git_blob_revision(metadata_ciphertext)
    raw_path = f"MooMooAU/Manifests/raw/{'b' * 64}.json.age"
    config = TargetRepositoryConfig(repository_id=7_500_100, installation_id=8_500_100)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")

    class DriftTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            if request.url == content_url(locator, raw_path):
                return HttpResponse(
                    200,
                    json.dumps(
                        {
                            "path": raw_path,
                            "sha": revision,
                            "size": len(metadata_ciphertext),
                            "type": "file",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode(),
                )
            assert request.url == git_blob_url(locator, revision)
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "content": base64.b64encode(returned_ciphertext).decode("ascii"),
                        "encoding": "base64",
                        "sha": revision,
                        "size": len(returned_ciphertext),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )

    guard = GitHubEndpointGuard(DriftTransport(), config)
    guard.bind_repository(locator)
    token = InstallationToken(
        SecretText("synthetic-installation-token"),
        datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    try:
        store = GitHubAppendOnlyCiphertextStore(guard, locator, token)
        with pytest.raises(RawCommitError, match="blob revision differs"):
            store.fetch(raw_path)
    finally:
        token.destroy()


def test_t0705_processed_current_uses_canonical_git_blob_not_contents_media() -> None:
    ciphertext = _synthetic_age_envelope()
    revision = _git_blob_revision(ciphertext)
    pointer_path = f"MooMooAU/State/processed-current/{'a' * 64}.json.age"
    config = TargetRepositoryConfig(repository_id=7_500_101, installation_id=8_500_101)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")

    class ContentsMediaMismatchTransport:
        def __init__(self) -> None:
            self.requests: list[HttpRequest] = []

        def send(self, request: HttpRequest) -> HttpResponse:
            self.requests.append(request)
            if request.url == content_url(locator, pointer_path):
                assert dict(request.headers)["Accept"] == "application/vnd.github+json"
                return HttpResponse(
                    200,
                    json.dumps(
                        {
                            "content": base64.b64encode(
                                b"contents-inline-representation-differs"
                            ).decode("ascii"),
                            "encoding": "base64",
                            "path": pointer_path,
                            "sha": revision,
                            "size": len(ciphertext),
                            "type": "file",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode(),
                )
            assert request.url == git_blob_url(locator, revision)
            assert dict(request.headers)["Accept"] == "application/vnd.github+json"
            encoded = base64.b64encode(ciphertext).decode("ascii")
            wrapped = "\n".join(encoded[index : index + 60] for index in range(0, len(encoded), 60))
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "content": wrapped,
                        "encoding": "base64",
                        "sha": revision,
                        "size": len(ciphertext),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )

    transport = ContentsMediaMismatchTransport()
    guard = GitHubEndpointGuard(transport, config)
    guard.bind_repository(locator)
    token = InstallationToken(
        SecretText("synthetic-installation-token"),
        datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    try:
        recovered = GitHubProcessedCiphertextStore(
            guard,
            locator,
            token,
        ).fetch_current(pointer_path)
    finally:
        token.destroy()
    assert recovered == RevisionedCiphertext(ciphertext, revision)
    assert [request.url for request in transport.requests] == [
        content_url(locator, pointer_path),
        git_blob_url(locator, revision),
    ]
    assert all(
        dict(request.headers)["Accept"] == "application/vnd.github+json"
        for request in transport.requests
    )


def test_t0705_processed_current_fails_closed_on_canonical_blob_revision_drift() -> None:
    metadata_ciphertext = _synthetic_age_envelope()
    returned_ciphertext = metadata_ciphertext[:-1] + b"\x01"
    revision = _git_blob_revision(metadata_ciphertext)
    pointer_path = f"MooMooAU/State/processed-current/{'b' * 64}.json.age"
    config = TargetRepositoryConfig(repository_id=7_500_102, installation_id=8_500_102)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")

    class DriftTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            if request.url == content_url(locator, pointer_path):
                return HttpResponse(
                    200,
                    json.dumps(
                        {
                            "path": pointer_path,
                            "sha": revision,
                            "size": len(metadata_ciphertext),
                            "type": "file",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode(),
                )
            assert request.url == git_blob_url(locator, revision)
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "content": base64.b64encode(returned_ciphertext).decode("ascii"),
                        "encoding": "base64",
                        "sha": revision,
                        "size": len(returned_ciphertext),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )

    guard = GitHubEndpointGuard(DriftTransport(), config)
    guard.bind_repository(locator)
    token = InstallationToken(
        SecretText("synthetic-installation-token"),
        datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    try:
        store = GitHubProcessedCiphertextStore(guard, locator, token)
        with pytest.raises(ProcessedCommitError, match="blob revision differs"):
            store.fetch_current(pointer_path)
    finally:
        token.destroy()


def test_t0705_timeline_snapshot_recovery_allows_immutable_above_pointer_limit() -> None:
    ciphertext = _synthetic_age_envelope() + b"\x00" * (2 * 1024 * 1024)
    revision = _git_blob_revision(ciphertext)
    manifest_path = f"MooMooAU/Manifests/timeline/{'c' * 64}.json.age"
    config = TargetRepositoryConfig(repository_id=7_500_103, installation_id=8_500_103)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")

    class LargeImmutableTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            if request.url == content_url(locator, manifest_path):
                return HttpResponse(
                    200,
                    json.dumps(
                        {
                            "path": manifest_path,
                            "sha": revision,
                            "size": len(ciphertext),
                            "type": "file",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode(),
                )
            assert request.url == git_blob_url(locator, revision)
            encoded = base64.b64encode(ciphertext).decode("ascii")
            wrapped = "\n".join(encoded[index : index + 60] for index in range(0, len(encoded), 60))
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "content": wrapped,
                        "encoding": "base64",
                        "sha": revision,
                        "size": len(ciphertext),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )

    guard = GitHubEndpointGuard(LargeImmutableTransport(), config)
    guard.bind_repository(locator)
    token = InstallationToken(
        SecretText("synthetic-installation-token"),
        datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    try:
        recovered = GitHubProcessedCiphertextStore(
            guard,
            locator,
            token,
        ).fetch_immutable(manifest_path)
    finally:
        token.destroy()
    assert recovered == ciphertext


def test_t0705_processed_current_retains_narrow_ciphertext_limit() -> None:
    ciphertext = _synthetic_age_envelope() + b"\x00" * (2 * 1024 * 1024)
    revision = _git_blob_revision(ciphertext)
    pointer_path = f"MooMooAU/State/processed-current/{'c' * 64}.json.age"
    config = TargetRepositoryConfig(repository_id=7_500_104, installation_id=8_500_104)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")

    class OversizedPointerTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            assert request.url == content_url(locator, pointer_path)
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "path": pointer_path,
                        "sha": revision,
                        "size": len(ciphertext),
                        "type": "file",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )

    guard = GitHubEndpointGuard(OversizedPointerTransport(), config)
    guard.bind_repository(locator)
    token = InstallationToken(
        SecretText("synthetic-installation-token"),
        datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    try:
        store = GitHubProcessedCiphertextStore(guard, locator, token)
        with pytest.raises(ProcessedCommitError, match="current response is invalid"):
            store.fetch_current(pointer_path)
    finally:
        token.destroy()


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


def test_t0705_ga_quarantines_unverifiable_pre_raw_metadata_without_collateral() -> None:
    verified_id = "msg-stage7-ga-metadata-verified"
    quarantined_id = "msg-stage7-ga-metadata-unverifiable"
    with ga_context(
        (
            m3_canary_message(verified_id),
            m3_canary_message(quarantined_id),
        ),
        malformed_metadata_ids=frozenset((quarantined_id,)),
    ) as context:
        outcome = context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )

        result = outcome.result
        assert result.candidate_refs == 2
        assert result.metadata_reads == 3
        assert result.verified_candidates == result.raw_archived == 1
        assert result.quarantined_candidates == 1
        assert result.unknown_candidates == result.rejected_candidates == 0
        assert result.full_recovery_successes == 1
        assert result.mutation_calls == result.confirmed_trashed == 1
        assert result.pending_verified_refs == 0
        assert context.transport.inner.raw_fetches == [verified_id]
        assert context.transport.trashed_ids == [verified_id]
        assert context.raw_store.create_calls > 0
        assert context.processed_store.write_calls > 0
        assert context.checkpoint_store.commit_calls == 1
        assert context.timeline_remote.maximum_observed_asset_count == 1


def test_t0705_ga_keeps_unverifiable_prior_pending_source_for_replay() -> None:
    pending_id = "msg-stage7-ga-pending-unverifiable"
    verified_id = "msg-stage7-ga-pending-control"
    pending_ref = MessageRef(pending_id, "thread-" + pending_id)
    initial = SyncState(
        "9000",
        (
            MessageRef(verified_id, "thread-" + verified_id),
            pending_ref,
        ),
    )
    with ga_context(
        (
            m3_canary_message(pending_id),
            m3_canary_message(verified_id),
        ),
        initial_sync_state=initial,
        initial_pending_refs=(pending_ref,),
        malformed_metadata_ids=frozenset((pending_id,)),
    ) as context:
        outcome = context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )

        assert outcome.result.quarantined_candidates == 1
        assert outcome.result.pending_verified_refs == 1
        recovered = context.checkpoint.recover()
        assert recovered is not None
        assert recovered.checkpoint.pending_verified_refs == (pending_ref,)
        assert context.transport.inner.raw_fetches == [verified_id]
        assert context.transport.trashed_ids == [verified_id]


def test_t0705_ga_second_metadata_failure_stays_fail_closed_before_trash() -> None:
    message_id = "msg-stage7-ga-second-metadata-unverifiable"
    with ga_context(
        (m3_canary_message(message_id),),
        malformed_metadata_after_first_ids=frozenset((message_id,)),
    ) as context:
        with pytest.raises(MessageMetadataUnverifiable):
            context.runner.run(
                _sunday_plan(),
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
                beta_message_budget=1,
                ga_mutation_budget_per_run=1,
                ga_capacity_authorized=True,
            )

        assert context.transport.metadata_read_counts[message_id] == 2
        assert context.raw_store.create_calls > 0
        assert context.processed_store.write_calls > 0
        assert context.transport.trashed_ids == []
        assert context.checkpoint_store.commit_calls == 0
        assert "upload" not in context.timeline_remote.actions
        assert "delete" not in context.timeline_remote.actions


def test_t0705_ga_replays_persisted_labels_for_an_already_trashed_current_source() -> None:
    message_id = "msg-stage7-ga-historical-label-replay"
    message = replace(
        m3_canary_message(message_id),
        labels=("CATEGORY_UPDATES", "INBOX", "TRASH"),
    )
    historical_labels = ("CATEGORY_UPDATES", "INBOX")
    with ga_context(
        (message,),
        historical_label_state=historical_labels,
    ) as context:
        outcome = context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )

        assert context.first_import_timestamps.label_state_resolutions == 1
        assert len(context.processed_plan_factory.bundles) == 1
        bundle = context.processed_plan_factory.bundles[0]
        envelope_artifact = next(
            artifact
            for artifact in bundle.artifacts
            if artifact.dataset_name == "document_envelopes"
        )
        envelope = json.loads(envelope_artifact.plaintext)
        assert envelope["gmail"]["label_state"] == list(historical_labels)
        assert outcome.result.already_trashed == 1
        assert outcome.result.confirmed_trashed == outcome.result.mutation_calls == 0
        assert context.transport.trashed_ids == []


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


def test_t0705_ga_accepts_paired_empty_protected_registries_as_safe_deferred() -> None:
    message_id = "msg-stage7-ga-safe-deferred"
    with ga_context(
        (m3_canary_message(message_id),),
        safe_deferred_registries=True,
    ) as context:
        outcome = context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )

        assert outcome.result.processed_complete == 0
        assert outcome.result.processed_safe_deferred == 1
        assert outcome.result.full_recovery_successes == 1
        assert outcome.result.confirmed_trashed == outcome.result.mutation_calls == 1
        assert context.transport.trashed_ids == [message_id]
        assert outcome.result.final_live_timeline_assets == 1
        assert context.timeline_remote.maximum_observed_asset_count == 1
        assert outcome.result.sync_checkpoint_recoveries == 1


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


def _protected_ga_environment(head_sha: str) -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY_ID": str(CONTROL_REPOSITORY_ID),
        "GITHUB_REPOSITORY_OWNER_ID": str(CONTROL_OWNER_ID),
        "GITHUB_ACTOR_ID": str(CONTROL_OWNER_ID),
        "GITHUB_RUN_ID": "7005001",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": head_sha,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": CONTROL_WORKFLOW_REF,
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MOOMOOAU_PROTECTED_ENVIRONMENT": "moomooau-beta",
        "MOOMOOAU_GA_REHEARSAL_AUTHORIZED_HEAD": head_sha,
    }


class _SyntheticProductionRuntime:
    def __init__(self, execution: ProductionExecutionResult) -> None:
        self._execution = execution
        self.trigger: RunTrigger | None = None

    def run(self, trigger: RunTrigger) -> ProductionExecutionResult:
        self.trigger = trigger
        return self._execution


class _SyntheticProductionBootstrap:
    def __init__(self, execution: ProductionExecutionResult) -> None:
        self.runtime = _SyntheticProductionRuntime(execution)
        self.open_calls = 0

    @contextmanager
    def open(self) -> Iterator[_SyntheticProductionRuntime]:
        self.open_calls += 1
        yield self.runtime


def test_t0705_protected_contract_binds_exact_receipts_without_secret_reads() -> None:
    contract = execution_contract(PROJECT_ROOT)
    assert contract["mode"] == "CONTRACT_ONLY"
    assert contract["ga_authorized"] is True
    assert contract["required_event"] == "workflow_dispatch"
    assert (
        contract["required_confirmation"]
        == "GA_SCHEDULE_MODE_TIMELINE_SNAPSHOT_RECOVERY_MUTATION_BUDGET_ONE"
    )
    assert contract["schedule_mode"] == "SCHEDULE_REHEARSAL"
    assert contract["security_clock_mode"] == "LIVE_UTC"
    assert contract["schedule_clock_mode"] == "DETERMINISTIC_HISTORICAL_REPLAY_FIXTURE"
    assert contract["schedule_clock_fixture_utc"] == "2026-07-26T19:00:00Z"
    assert contract["platform_schedule_event_observed"] is False
    assert contract["target_time"] == "04:30"
    assert contract["timezone"] == "Australia/Sydney"
    assert contract["ga_mutation_budget_per_run"] == 1
    assert contract["maximum_pipeline_runs"] == 1
    assert contract["maximum_reruns"] == 0
    assert contract["required_protected_input_count"] == 8
    assert contract["blue_green_receipt_sha256"] == blue_green_receipt_sha256(PROJECT_ROOT)
    assert len(cast(list[str], contract["failed_ga_head_shas"])) == 9
    assert len(cast(list[str], contract["failed_ga_preflight_head_shas"])) == 1
    assert len(cast(list[str], contract["failed_ga_authority_context_head_shas"])) == 1
    assert len(cast(list[str], contract["failed_ga_schedule_planning_head_shas"])) == 1
    assert len(cast(list[str], contract["failed_ga_authentication_clock_head_shas"])) == 1
    assert len(cast(list[str], contract["failed_ga_raw_recovery_head_shas"])) == 1
    assert len(cast(list[str], contract["failed_ga_trash_confirmation_head_shas"])) == 1
    assert len(cast(list[str], contract["failed_ga_timeline_snapshot_recovery_head_shas"])) == 1
    assert contract["failed_ga_heads_rerun_allowed"] is False
    assert contract["failed_ga_heads_redispatch_allowed"] is False
    assert len(cast(list[str], contract["failed_ga_attempt_ledger_paths"])) == 9
    assert contract["failed_ga_preflight_ledger_path"] == (
        "machine/stages/S7/reviews/t0705/canonical-blob-preflight-attempt-ledger.json"
    )
    assert contract["failed_ga_authority_context_ledger_path"] == (
        "machine/stages/S7/reviews/t0705/authority-variable-scope-attempt-ledger.json"
    )
    assert contract["failed_ga_schedule_planning_ledger_path"] == (
        "machine/stages/S7/reviews/t0705/schedule-planning-clock-attempt-ledger.json"
    )
    assert contract["failed_ga_authentication_clock_ledger_path"] == (
        "machine/stages/S7/reviews/t0705/authentication-clock-coupling-attempt-ledger.json"
    )
    assert contract["failed_ga_raw_recovery_ledger_path"] == (
        "machine/stages/S7/reviews/t0705/raw-recovery-representation-attempt-ledger.json"
    )
    assert contract["failed_ga_trash_confirmation_ledger_path"] == (
        "machine/stages/S7/reviews/t0705/trash-confirmation-attempt-ledger.json"
    )
    assert contract["ga_gate_sha256"] == ga_gate_sha256(PROJECT_ROOT)


def test_t0705_rehearsal_clock_is_deterministic_historical_replay_after_target() -> None:
    assert GA_REHEARSAL_CLOCK_UTC == datetime(2026, 7, 26, 19, tzinfo=UTC)
    plan = RunPlanner().plan(
        RunTrigger.SCHEDULE,
        started_at_utc=GA_REHEARSAL_CLOCK_UTC,
        last_successful_run_date_sydney=None,
    )
    assert plan.run_date_sydney == date(2026, 7, 27)
    assert plan.schedule_delay_minutes == 30


def test_t0705_derives_ga_config_in_memory_from_existing_beta_plane() -> None:
    beta_config = {
        "schema_version": "moomooau.protected-beta-config.v1",
        "phase": "BETA_RAW_ONLY",
        "beta_message_budget": 1,
        "key_epoch": "synthetic-epoch-1",
        "age_recipient": "age1" + "q" * 58,
        "github": {
            "app_id": 1,
            "installation_id": 2,
            "repository_id": 3,
        },
        "capacity": {
            "observed_at_utc": "2026-07-23T00:00:00Z",
            "limits": {
                "lfs_storage_budget_bytes": 10_000_000,
                "lfs_object_maximum_bytes": 1_000_000,
            },
            "snapshot": {
                "git_repository_bytes": 1_000,
                "lfs_storage_bytes": 0,
                "largest_git_object_bytes": 1_000,
                "largest_lfs_object_bytes": 0,
                "live_release_asset_bytes": 1_000,
            },
        },
    }
    source = DerivedGASecretSource(
        {"MOOMOOAU_BETA_CONFIG": json.dumps(beta_config)},
        observations_through(ReleasePhase.BLUE_GREEN),
    )
    derived = source.read(PRODUCTION_CONFIG_SECRET_NAME)
    try:
        parsed = json.loads(derived.reveal())
    finally:
        derived.destroy()
    assert parsed["schema_version"] == "moomooau.production-config.v1"
    assert parsed["phase"] == "GA"
    assert parsed["parser_current_version"] == "1.0.0"
    assert parsed["ga_mutation_budget_per_run"] == 1
    assert parsed["github"] == beta_config["github"]
    assert parsed["capacity"] == beta_config["capacity"]
    assert [item["phase"] for item in parsed["predecessor_observations"]] == [
        "ALPHA",
        "BETA_RAW_ONLY",
        "M3_CANARY",
        "BLUE_GREEN",
    ]
    assert "MOOMOOAU_BETA_CONFIG" not in derived.__repr__()


def test_t0705_protected_context_rejects_non_owner_before_bootstrap() -> None:
    head = "a" * 40
    environment = _protected_ga_environment(head)
    environment["GITHUB_ACTOR_ID"] = "1"
    synthetic = _SyntheticProductionBootstrap(cast(ProductionExecutionResult, object()))
    with pytest.raises(ProtectedGAEntrypointError, match="context"):
        execute_protected(
            environment,
            project_root=PROJECT_ROOT,
            expected_head_sha=head,
            supplied_blue_green_receipt_sha256=blue_green_receipt_sha256(PROJECT_ROOT),
            supplied_ga_gate_sha256=ga_gate_sha256(PROJECT_ROOT),
            confirmation=GA_CONFIRMATION,
            bootstrap=cast(ProductionBootstrap, synthetic),
        )
    assert synthetic.open_calls == 0


def test_t0705_protected_schedule_rehearsal_is_aggregate_only_and_gate_complete() -> None:
    message_id = "msg-stage7-protected-ga"
    predecessors = observations_through(ReleasePhase.BLUE_GREEN)
    with ga_context((m3_canary_message(message_id),)) as context:
        outcome = context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=predecessors,
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )
        execution = ProductionExecutionResult(_sunday_plan(), outcome)
        synthetic = _SyntheticProductionBootstrap(execution)
        head = "b" * 40
        evidence = execute_protected(
            _protected_ga_environment(head),
            project_root=PROJECT_ROOT,
            expected_head_sha=head,
            supplied_blue_green_receipt_sha256=blue_green_receipt_sha256(PROJECT_ROOT),
            supplied_ga_gate_sha256=ga_gate_sha256(PROJECT_ROOT),
            confirmation=GA_CONFIRMATION,
            bootstrap=cast(ProductionBootstrap, synthetic),
            clock=lambda: datetime(2026, 7, 26, 1, tzinfo=UTC),
        )
    public = evidence.to_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["status"] == "PROTECTED_GA_SCHEDULE_REHEARSAL_COMPLETED_NOT_FINAL"
    assert public["ga_gate_status"] == "PASS"
    assert public["schedule"] == {
        "mode": "SCHEDULE_REHEARSAL",
        "target_time": "04:30",
        "timezone": "Australia/Sydney",
        "planner_trigger": "schedule",
        "platform_schedule_event_observed": False,
        "workflow_dispatch_truthfully_disclosed": True,
        "fixed_calendar_wait_days": 0,
    }
    phase = cast(dict[str, object], public["phase_observation"])
    assert phase["verified_bucket"] == "ONE"
    assert phase["source_mutation_budget"] == 1
    assert phase["remote_recovery_one_hundred_percent"] is True
    assert phase["full_reconcile_comparison"] == "NOT_COMPARABLE_INITIAL_IMPORT"
    assert phase["minimum_live_timeline_assets"] == 1
    assert phase["maximum_live_timeline_assets"] == 1
    assert phase["exact_mailbox_counts_disclosed"] is False
    assert public["production_health_claimed"] is False
    assert public["final_acceptance_claimed"] is False
    assert synthetic.open_calls == 1
    assert synthetic.runtime.trigger is RunTrigger.SCHEDULE
    assert message_id not in encoded
    assert "synthetic-private" not in encoded


def test_t0705_ga_diagnostics_are_closed_and_reach_checkpoint_commit() -> None:
    diagnostics = ProtectedGADiagnostics()
    with pytest.raises(TypeError, match="phase"):
        diagnostics.enter(cast(ProtectedGAFailurePhase, "FULL_RECOVERY"))

    with ga_context(
        (m3_canary_message("msg-stage7-ga-diagnostics"),),
        diagnostics=diagnostics,
    ) as context:
        context.runner.run(
            _sunday_plan(),
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
            beta_message_budget=1,
            ga_mutation_budget_per_run=1,
            ga_capacity_authorized=True,
        )

    assert diagnostics.phase is ProtectedGAFailurePhase.CHECKPOINT_COMMIT
    payload = public_failure_payload(diagnostics)
    assert payload["reason_code"] == "PROTECTED_GA_CHECKPOINT_COMMIT_FAILED"
    assert payload["diagnostic_taxonomy"] == FAILURE_TAXONOMY_VERSION
    assert payload["exact_root_cause_claimed"] is False
    assert payload["protected_values_disclosed"] is False
    assert "msg-stage7-ga-diagnostics" not in json.dumps(payload, sort_keys=True)


def test_t0705_ga_diagnostics_narrow_processed_plan_without_exception_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = ProtectedGADiagnostics()
    protected_value = "synthetic-private-replay-value"

    def fail_first_import(*args: object, **kwargs: object) -> datetime:
        del args, kwargs
        raise GARuntimeError(protected_value)

    with ga_context(
        (m3_canary_message("msg-stage7-ga-processed-plan-diagnostics"),),
        diagnostics=diagnostics,
    ) as context:
        monkeypatch.setattr(context.first_import_timestamps, "resolve", fail_first_import)
        with pytest.raises(GARuntimeError, match=protected_value):
            context.runner.run(
                _sunday_plan(),
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                predecessor_observations=observations_through(ReleasePhase.BLUE_GREEN),
                beta_message_budget=1,
                ga_mutation_budget_per_run=1,
                ga_capacity_authorized=True,
            )

    assert diagnostics.phase is ProtectedGAFailurePhase.FIRST_IMPORT_RECOVERY
    payload = public_failure_payload(diagnostics)
    assert payload["reason_code"] == "PROTECTED_GA_FIRST_IMPORT_RECOVERY_FAILED"
    assert protected_value not in json.dumps(payload, sort_keys=True)


def test_t0705_first_import_diagnostics_narrow_pointer_decrypt_without_value_leak() -> None:
    diagnostics = ProtectedGADiagnostics()
    protected_value = "synthetic-private-first-import-value"

    class Store:
        def fetch_current(self, relative_path: str) -> RevisionedCiphertext:
            assert relative_path.startswith("MooMooAU/State/processed-current/")
            return RevisionedCiphertext(_synthetic_age_envelope(), "a" * 40)

    class Decryptor:
        def decrypt(self, ciphertext: bytes) -> bytes:
            assert ciphertext == _synthetic_age_envelope()
            raise RuntimeError(protected_value)

    source = RemoteFirstImportTimestampSource(  # type: ignore[arg-type]
        Store(),
        Decryptor(),
        diagnostics,
    )
    with pytest.raises(ProductionAdapterError, match="pointer recovery"):
        source.resolve("a" * 64, datetime(2026, 7, 26, 8, 30, tzinfo=UTC))

    assert diagnostics.phase is ProtectedGAFailurePhase.FIRST_IMPORT_POINTER_DECRYPT
    payload = public_failure_payload(diagnostics)
    assert payload["reason_code"] == "PROTECTED_GA_FIRST_IMPORT_POINTER_DECRYPT_FAILED"
    assert protected_value not in json.dumps(payload, sort_keys=True)


def test_t0705_label_recovery_does_not_misreport_first_import_subphase() -> None:
    diagnostics = ProtectedGADiagnostics()

    class EmptyStore:
        def fetch_current(self, relative_path: str) -> None:
            assert relative_path.startswith("MooMooAU/State/processed-current/")
            return None

    class UnusedDecryptor:
        def decrypt(self, ciphertext: bytes) -> bytes:
            raise AssertionError("decrypt must not be called for an absent current pointer")

    diagnostics.enter(ProtectedGAFailurePhase.HISTORICAL_LABEL_RECOVERY)
    source = RemoteFirstImportTimestampSource(  # type: ignore[arg-type]
        EmptyStore(),
        UnusedDecryptor(),
        diagnostics,
    )
    assert (
        source.resolve_label_state(
            "a" * 64,
            datetime(2026, 7, 26, 8, 30, tzinfo=UTC),
        )
        is None
    )
    assert diagnostics.phase is ProtectedGAFailurePhase.HISTORICAL_LABEL_RECOVERY


def test_t0705_ga_main_redacts_exception_and_emits_only_safe_phase(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    protected_value = "private-repository-and-message-identifier"

    def fail_after_full_recovery(*args: object, **kwargs: object) -> object:
        del args
        diagnostics = cast(ProtectedGADiagnostics, kwargs["diagnostics"])
        assert kwargs.get("clock") is None
        schedule_clock = cast(Callable[[], datetime], kwargs["schedule_clock"])
        assert schedule_clock() == GA_REHEARSAL_CLOCK_UTC
        diagnostics.enter(ProtectedGAFailurePhase.FULL_RECOVERY)
        raise RuntimeError(protected_value)

    monkeypatch.setattr(
        protected_ga_entrypoint,
        "execute_protected",
        fail_after_full_recovery,
    )
    result = protected_ga_entrypoint.main(
        [
            "--execute-protected",
            "--project-root",
            str(PROJECT_ROOT),
            "--expected-head-sha",
            "d" * 40,
            "--blue-green-receipt-sha256",
            "e" * 64,
            "--ga-gate-sha256",
            "f" * 64,
            "--confirm",
            GA_CONFIRMATION,
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 2
    assert payload["failure_phase"] == "FULL_RECOVERY"
    assert payload["reason_code"] == "PROTECTED_GA_FULL_RECOVERY_FAILED"
    assert payload["exact_root_cause_claimed"] is False
    assert protected_value not in output
