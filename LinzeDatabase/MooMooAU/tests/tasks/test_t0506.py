from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from stage5_support import recovery_context, timeline_event

from moomooau_archive.adapters import EphemeralAgeSession
from moomooau_archive.github_guard import (
    LIVE_ASSET_NAME,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    RepositoryLocator,
    TargetRepositoryConfig,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.m3 import M3State
from moomooau_archive.timeline_publish import (
    MemoryTimelineReleaseRemote,
    MemoryTimelineStateStore,
    SingleLatestTimelinePublisher,
    TimelinePublishAction,
    TimelinePublishError,
    TimelinePublishStateName,
)
from moomooau_archive.timeline_render import DeterministicTimelineRenderer


class CountingRenderer:
    def __init__(self) -> None:
        self.delegate = DeterministicTimelineRenderer()
        self.calls = 0

    def render(self, events, processed_snapshot_root):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.delegate.render(events, processed_snapshot_root)


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(201, b"{}")


def test_t0506_same_snapshot_refetches_decrypts_and_performs_no_render_or_mutation() -> None:
    with recovery_context() as context, EphemeralAgeSession() as crypto:
        event = timeline_event(context)
        renderer = CountingRenderer()
        remote = MemoryTimelineReleaseRemote()
        state_store = MemoryTimelineStateStore()
        publisher = SingleLatestTimelinePublisher(renderer, crypto, remote, state_store)
        first = publisher.publish(
            (event,),
            processed_snapshot_root="1" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )
        before_actions = tuple(remote.actions)
        second = publisher.publish(
            (event,),
            processed_snapshot_root="1" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 20, 1, tzinfo=UTC),
        )
        assert first.state is TimelinePublishStateName.HEALTHY
        assert second.action is TimelinePublishAction.NO_CHANGE
        assert second.render_calls == 0
        assert second.asset_mutations == 0
        assert renderer.calls == 1
        assert state_store.commit_calls == 1
        assert tuple(remote.actions) != before_actions  # remote recovery reads still occurred
        assert len(remote.list_assets(remote.release_id)) == 1
        assert remote.list_assets(remote.release_id)[0].name == LIVE_ASSET_NAME


def test_t0506_changed_plaintext_serially_deletes_then_uploads_and_never_exceeds_one() -> None:
    with recovery_context() as context, EphemeralAgeSession() as crypto:
        event = timeline_event(context)
        changed = replace(event, m3_state=M3State.ALREADY_TRASHED)
        renderer = CountingRenderer()
        remote = MemoryTimelineReleaseRemote()
        state_store = MemoryTimelineStateStore()
        publisher = SingleLatestTimelinePublisher(renderer, crypto, remote, state_store)
        publisher.publish(
            (event,),
            processed_snapshot_root="2" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )
        remote.actions.clear()
        result = publisher.publish(
            (changed,),
            processed_snapshot_root="3" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 21, tzinfo=UTC),
        )
        assert result.action is TimelinePublishAction.ASSET_REPLACED
        assert result.asset_mutations == 2
        assert remote.actions.index("delete") < remote.actions.index("upload")
        assert remote.maximum_observed_asset_count <= 1
        assert len(remote.list_assets(remote.release_id)) == 1


def test_t0506_delete_then_upload_failure_records_zero_asset_and_repairs_same_snapshot_first() -> (
    None
):
    with recovery_context() as context, EphemeralAgeSession() as crypto:
        event = timeline_event(context)
        changed = replace(event, m3_state=M3State.ALREADY_TRASHED)
        renderer = CountingRenderer()
        remote = MemoryTimelineReleaseRemote()
        state_store = MemoryTimelineStateStore()
        publisher = SingleLatestTimelinePublisher(renderer, crypto, remote, state_store)
        publisher.publish(
            (event,),
            processed_snapshot_root="4" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )
        remote.fail_next_upload = True
        failed = publisher.publish(
            (changed,),
            processed_snapshot_root="5" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 21, tzinfo=UTC),
        )
        assert failed.action is TimelinePublishAction.REPAIR_REQUIRED
        assert failed.state is TimelinePublishStateName.TIMELINE_REPAIR_REQUIRED
        assert failed.asset_count == 0
        assert remote.list_assets(remote.release_id) == ()
        with pytest.raises(TimelinePublishError, match="replayed first"):
            publisher.publish(
                (changed,),
                processed_snapshot_root="6" * 64,
                key_epoch="synthetic-epoch-1",
                now_utc=datetime(2026, 7, 22, tzinfo=UTC),
            )
        repaired = publisher.publish(
            (changed,),
            processed_snapshot_root="5" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 22, 1, tzinfo=UTC),
        )
        assert repaired.action is TimelinePublishAction.ASSET_REPAIRED
        assert repaired.asset_count == 1
        assert remote.maximum_observed_asset_count <= 1


def test_t0506_uncertain_or_corrupt_upload_converges_without_stranded_asset() -> None:
    with recovery_context() as context, EphemeralAgeSession() as crypto:
        event = timeline_event(context)
        remote = MemoryTimelineReleaseRemote()
        remote.raise_after_next_upload = True
        publisher = SingleLatestTimelinePublisher(
            CountingRenderer(),
            crypto,
            remote,
            MemoryTimelineStateStore(),
        )
        recovered = publisher.publish(
            (event,),
            processed_snapshot_root="7" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )
        assert recovered.state is TimelinePublishStateName.HEALTHY
        assert recovered.reason_code == "UPLOAD_RESPONSE_UNKNOWN_REMOTE_RECOVERY_VERIFIED"
        assert len(remote.list_assets(remote.release_id)) == 1
        assert remote.maximum_observed_asset_count <= 1

        transport = RecordingTransport()
        config = TargetRepositoryConfig(repository_id=7_500_001, installation_id=8_500_001)
        guard = GitHubEndpointGuard(transport, config)
        locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")
        guard.bind_repository(locator)
        fixed_upload = (
            "https://uploads.github.com/repos/synthetic-owner/synthetic-target/"
            "releases/501/assets?name=timeline-latest.png.age"
        )
        with pytest.raises(GitHubBoundaryError):
            guard.send(HttpRequest("POST", fixed_upload, body=b"synthetic plaintext"))
        with pytest.raises(GitHubBoundaryError):
            guard.send(
                HttpRequest(
                    "POST",
                    fixed_upload.replace("timeline-latest.png.age", "timeline-history.png.age"),
                    body=crypto.encrypt(b"synthetic timeline"),
                )
            )
        assert transport.requests == []

    with recovery_context() as context, EphemeralAgeSession() as crypto:
        event = timeline_event(context)
        remote = MemoryTimelineReleaseRemote()
        remote.corrupt_next_upload_storage = True
        publisher = SingleLatestTimelinePublisher(
            CountingRenderer(),
            crypto,
            remote,
            MemoryTimelineStateStore(),
        )
        quarantined = publisher.publish(
            (event,),
            processed_snapshot_root="8" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )
        assert quarantined.state is TimelinePublishStateName.TIMELINE_REPAIR_REQUIRED
        assert quarantined.asset_count == 0
        assert remote.list_assets(remote.release_id) == ()
        repaired = publisher.publish(
            (event,),
            processed_snapshot_root="8" * 64,
            key_epoch="synthetic-epoch-1",
            now_utc=datetime(2026, 7, 20, 1, tzinfo=UTC),
        )
        assert repaired.state is TimelinePublishStateName.HEALTHY
        assert repaired.asset_count == 1
        assert remote.maximum_observed_asset_count <= 1
