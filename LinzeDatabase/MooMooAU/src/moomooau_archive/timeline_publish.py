"""Single encrypted live Timeline Release Asset protocol and deterministic repair."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast

from .adapters import is_age_envelope
from .github_guard import (
    CONTENT_TIMELINE_STATE_MESSAGE,
    GITHUB_API_ORIGIN,
    GITHUB_API_VERSION,
    GITHUB_UPLOAD_ORIGIN,
    LIVE_ASSET_NAME,
    LIVE_RELEASE_TAG,
    TIMELINE_STATE_PATH,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    InstallationToken,
    RepositoryLocator,
    content_url,
)
from .http_boundary import HttpRequest
from .timeline_event import TimelineEvent
from .timeline_render import RenderedTimeline, TimelineRendererPort

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAXIMUM_TIMELINE_ASSET_CIPHERTEXT_BYTES = 64 * 1024 * 1024
MAXIMUM_TIMELINE_STATE_CIPHERTEXT_BYTES = 1024 * 1024
MAXIMUM_TIMELINE_STATE_MUTATIONS_PER_PUBLISH = 4


class TimelinePublishError(RuntimeError):
    """Timeline remote state is unsafe or unverifiable; diagnostics remain redacted."""


class TimelinePublishStateName(StrEnum):
    HEALTHY = "HEALTHY"
    TIMELINE_REPAIR_REQUIRED = "TIMELINE_REPAIR_REQUIRED"


class TimelinePublishAction(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    STATE_REPAIRED = "STATE_REPAIRED"
    ASSET_REPLACED = "ASSET_REPLACED"
    ASSET_REPAIRED = "ASSET_REPAIRED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    asset_id: int
    name: str
    state: str
    size: int

    def __post_init__(self) -> None:
        if (
            type(self.asset_id) is not int
            or self.asset_id <= 0
            or not self.name
            or len(self.name) > 255
            or self.state not in {"uploaded", "starter"}
            or type(self.size) is not int
            or self.size < 0
        ):
            raise TimelinePublishError("Release Asset metadata is invalid")


@dataclass(frozen=True, slots=True, repr=False)
class TimelinePrivatePublishState:
    processed_snapshot_root: str
    timeline_plaintext_sha256: str
    timeline_ciphertext_sha256: str
    release_asset_id: int | None
    publish_state: TimelinePublishStateName
    verified_at_utc: datetime
    key_epoch: str

    def __post_init__(self) -> None:
        offset = self.verified_at_utc.utcoffset()
        if (
            _SHA256.fullmatch(self.processed_snapshot_root) is None
            or _SHA256.fullmatch(self.timeline_plaintext_sha256) is None
            or _SHA256.fullmatch(self.timeline_ciphertext_sha256) is None
            or (
                self.release_asset_id is not None
                and (type(self.release_asset_id) is not int or self.release_asset_id <= 0)
            )
            or (self.publish_state is TimelinePublishStateName.HEALTHY)
            != (self.release_asset_id is not None)
            or self.verified_at_utc.tzinfo is None
            or offset is None
            or offset.total_seconds() != 0
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
        ):
            raise TimelinePublishError("private Timeline publish state is invalid")

    def __repr__(self) -> str:
        return (
            "TimelinePrivatePublishState(processed_snapshot_root=<redacted>, "
            "timeline_plaintext_sha256=<redacted>, timeline_ciphertext_sha256=<redacted>, "
            "release_asset_id=<redacted>, "
            f"publish_state={self.publish_state.value!r}, "
            "verified_at_utc=<redacted>, key_epoch=<redacted>)"
        )

    def to_bytes(self) -> bytes:
        return _canonical_json(
            {
                "schema_version": "moomooau.timeline-private-publish-state.v1",
                "processed_snapshot_root": self.processed_snapshot_root,
                "timeline_plaintext_sha256": self.timeline_plaintext_sha256,
                "timeline_ciphertext_sha256": self.timeline_ciphertext_sha256,
                "release_asset_id": self.release_asset_id,
                "release_asset_name": LIVE_ASSET_NAME,
                "release_tag": LIVE_RELEASE_TAG,
                "publish_state": self.publish_state.value,
                "verified_at_utc": _utc_text(self.verified_at_utc),
                "key_epoch": self.key_epoch,
            }
        )

    @classmethod
    def from_bytes(cls, payload: bytes) -> TimelinePrivatePublishState:
        if len(payload) > 1024 * 1024:
            raise TimelinePublishError("private Timeline state exceeds the safe limit")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TimelinePublishError("private Timeline state is invalid JSON") from exc
        required = {
            "schema_version",
            "processed_snapshot_root",
            "timeline_plaintext_sha256",
            "timeline_ciphertext_sha256",
            "release_asset_id",
            "release_asset_name",
            "release_tag",
            "publish_state",
            "verified_at_utc",
            "key_epoch",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("schema_version") != "moomooau.timeline-private-publish-state.v1"
            or value.get("release_asset_name") != LIVE_ASSET_NAME
            or value.get("release_tag") != LIVE_RELEASE_TAG
        ):
            raise TimelinePublishError("private Timeline state schema is invalid")
        raw_id = value.get("release_asset_id")
        if raw_id is not None and type(raw_id) is not int:
            raise TimelinePublishError("private Timeline state asset ID is invalid")
        try:
            return cls(
                processed_snapshot_root=_required_string(value, "processed_snapshot_root"),
                timeline_plaintext_sha256=_required_string(value, "timeline_plaintext_sha256"),
                timeline_ciphertext_sha256=_required_string(value, "timeline_ciphertext_sha256"),
                release_asset_id=raw_id,
                publish_state=TimelinePublishStateName(_required_string(value, "publish_state")),
                verified_at_utc=_parse_utc(_required_string(value, "verified_at_utc")),
                key_epoch=_required_string(value, "key_epoch"),
            )
        except ValueError as exc:
            raise TimelinePublishError("private Timeline state enum is invalid") from exc


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedTimelineState:
    ciphertext: bytes = field(repr=False)
    revision: str

    def __post_init__(self) -> None:
        if not is_age_envelope(self.ciphertext) or _REVISION.fullmatch(self.revision) is None:
            raise TimelinePublishError("encrypted Timeline state is invalid")


class TimelineCrypto(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> bytes: ...


class TimelineReleaseRemote(Protocol):
    def ensure_release(self) -> int: ...

    def list_assets(self, release_id: int) -> tuple[ReleaseAsset, ...]: ...

    def download(self, asset_id: int) -> bytes: ...

    def delete(self, asset_id: int) -> None: ...

    def upload(self, release_id: int, name: str, ciphertext: bytes) -> ReleaseAsset: ...


class TimelineStateStore(Protocol):
    def read(self) -> EncryptedTimelineState | None: ...

    def compare_and_swap(
        self,
        expected_revision: str | None,
        ciphertext: bytes,
    ) -> EncryptedTimelineState: ...


@dataclass(frozen=True, slots=True)
class TimelinePublishResult:
    action: TimelinePublishAction
    state: TimelinePublishStateName
    asset_count: int
    render_calls: int
    asset_mutations: int
    state_commits: int
    reason_code: str

    def __post_init__(self) -> None:
        if (
            self.asset_count not in {0, 1}
            or self.render_calls not in {0, 1}
            or self.asset_mutations not in {0, 1, 2, 3}
            or self.state_commits not in {0, 1}
            or (self.state is TimelinePublishStateName.HEALTHY) != (self.asset_count == 1)
            or not self.reason_code
        ):
            raise TimelinePublishError("Timeline publish result is inconsistent")


class SingleLatestTimelinePublisher:
    """Serial replace; healthy exactly one, repair exactly zero, never more than one."""

    def __init__(
        self,
        renderer: TimelineRendererPort,
        crypto: TimelineCrypto,
        remote: TimelineReleaseRemote,
        state_store: TimelineStateStore,
    ) -> None:
        self._renderer = renderer
        self._crypto = crypto
        self._remote = remote
        self._state_store = state_store

    def recover_committed_snapshot_root(self) -> str | None:
        """Recover the cross-run snapshot head or prove this is an empty first publish."""

        release_id = self._remote.ensure_release()
        assets = self._validated_assets(release_id)
        state = self._decode_state(self._state_store.read())
        if state is None:
            if assets:
                raise TimelinePublishError(
                    "Timeline Asset exists without a recoverable private snapshot head"
                )
            return None
        if state.publish_state is TimelinePublishStateName.HEALTHY:
            if not self._same_state_is_healthy(
                state,
                assets,
                state.processed_snapshot_root,
            ):
                raise TimelinePublishError("committed Timeline snapshot head is not healthy")
        elif assets:
            raise TimelinePublishError("Timeline repair snapshot must have zero live Assets")
        return state.processed_snapshot_root

    def publish(
        self,
        events: tuple[TimelineEvent, ...],
        *,
        processed_snapshot_root: str,
        key_epoch: str,
        now_utc: datetime,
    ) -> TimelinePublishResult:
        now = _require_utc(now_utc)
        if (
            _SHA256.fullmatch(processed_snapshot_root) is None
            or _KEY_EPOCH.fullmatch(key_epoch) is None
        ):
            raise TimelinePublishError("Timeline publish identity is invalid")
        release_id = self._remote.ensure_release()
        assets = self._validated_assets(release_id)
        encrypted_state = self._state_store.read()
        state = self._decode_state(encrypted_state)
        if (
            state is not None
            and state.publish_state is TimelinePublishStateName.TIMELINE_REPAIR_REQUIRED
            and state.processed_snapshot_root != processed_snapshot_root
        ):
            raise TimelinePublishError("the recorded repair snapshot must be replayed first")

        if state is not None and self._same_state_is_healthy(
            state,
            assets,
            processed_snapshot_root,
        ):
            return TimelinePublishResult(
                TimelinePublishAction.NO_CHANGE,
                TimelinePublishStateName.HEALTHY,
                1,
                0,
                0,
                0,
                "SAME_SNAPSHOT_REMOTE_RECOVERY_VERIFIED",
            )

        rendered = self._renderer.render(events, processed_snapshot_root)
        if rendered.processed_snapshot_root != processed_snapshot_root:
            raise TimelinePublishError("renderer returned a different Processed snapshot")
        current_ciphertext: bytes | None = None
        if assets:
            current_ciphertext = self._download_verified_envelope(assets[0])
            try:
                current_plaintext = self._crypto.decrypt(current_ciphertext)
            except Exception as exc:
                raise TimelinePublishError("current Timeline asset cannot be decrypted") from exc
            if hashlib.sha256(current_plaintext).hexdigest() == rendered.timeline_plaintext_sha256:
                healthy = self._healthy_state(
                    rendered,
                    hashlib.sha256(current_ciphertext).hexdigest(),
                    assets[0].asset_id,
                    now,
                    key_epoch,
                )
                self._commit_state(encrypted_state, healthy)
                return TimelinePublishResult(
                    TimelinePublishAction.STATE_REPAIRED,
                    TimelinePublishStateName.HEALTHY,
                    1,
                    1,
                    0,
                    1,
                    "REMOTE_PLAINTEXT_SAME_STATE_REPAIRED",
                )

        candidate = self._crypto.encrypt(rendered.png)
        if (
            not is_age_envelope(candidate)
            or len(candidate) > MAXIMUM_TIMELINE_ASSET_CIPHERTEXT_BYTES
        ):
            raise TimelinePublishError("candidate Timeline is not age encrypted")
        try:
            local_roundtrip = self._crypto.decrypt(candidate)
        except Exception as exc:
            raise TimelinePublishError("candidate Timeline round-trip failed") from exc
        if (
            local_roundtrip != rendered.png
            or hashlib.sha256(local_roundtrip).hexdigest() != rendered.timeline_plaintext_sha256
        ):
            raise TimelinePublishError("candidate Timeline plaintext digest differs")
        candidate_digest = hashlib.sha256(candidate).hexdigest()

        mutations = 0
        was_repair = not assets or (
            state is not None
            and state.publish_state is TimelinePublishStateName.TIMELINE_REPAIR_REQUIRED
        )
        if assets:
            latest_assets = self._validated_assets(release_id)
            if len(latest_assets) != 1 or latest_assets[0].asset_id != assets[0].asset_id:
                raise TimelinePublishError("current Timeline Asset changed before deletion")
            latest_ciphertext = self._download_verified_envelope(latest_assets[0])
            if current_ciphertext is None or latest_ciphertext != current_ciphertext:
                raise TimelinePublishError("current Timeline ciphertext changed before deletion")
            self._remote.delete(assets[0].asset_id)
            mutations += 1
            if self._validated_assets(release_id):
                raise TimelinePublishError("deleted Timeline Asset still exists")

        mutations += 1
        try:
            uploaded = self._remote.upload(release_id, LIVE_ASSET_NAME, candidate)
        except Exception as upload_error:
            remaining = self._validated_assets(release_id)
            if remaining:
                recovered = self._candidate_is_recoverable(
                    remaining[0],
                    candidate_digest,
                    rendered.timeline_plaintext_sha256,
                )
                if recovered:
                    healthy = self._healthy_state(
                        rendered,
                        candidate_digest,
                        remaining[0].asset_id,
                        now,
                        key_epoch,
                    )
                    self._commit_state(encrypted_state, healthy)
                    return TimelinePublishResult(
                        (
                            TimelinePublishAction.ASSET_REPAIRED
                            if was_repair
                            else TimelinePublishAction.ASSET_REPLACED
                        ),
                        TimelinePublishStateName.HEALTHY,
                        1,
                        1,
                        mutations,
                        1,
                        "UPLOAD_RESPONSE_UNKNOWN_REMOTE_RECOVERY_VERIFIED",
                    )
            return self._transition_to_repair(
                release_id,
                encrypted_state,
                rendered,
                candidate_digest,
                now,
                key_epoch,
                mutations,
                "UPLOAD_FAILED_ZERO_ASSET_REPAIR",
                cause=upload_error,
            )

        try:
            final_assets = self._validated_assets(release_id)
            if len(final_assets) != 1 or final_assets[0] != uploaded:
                raise TimelinePublishError("uploaded Timeline Asset did not converge to one")
            remote_candidate = self._download_verified_envelope(uploaded)
            if hashlib.sha256(remote_candidate).hexdigest() != candidate_digest:
                raise TimelinePublishError("remote Timeline transport verification failed")
            remote_plaintext = self._crypto.decrypt(remote_candidate)
            if hashlib.sha256(remote_plaintext).hexdigest() != rendered.timeline_plaintext_sha256:
                raise TimelinePublishError("remote Timeline plaintext digest differs")
        except Exception as recovery_error:
            return self._transition_to_repair(
                release_id,
                encrypted_state,
                rendered,
                candidate_digest,
                now,
                key_epoch,
                mutations,
                "UPLOADED_ASSET_RECOVERY_FAILED_ZERO_ASSET_REPAIR",
                cause=recovery_error,
            )

        healthy = self._healthy_state(
            rendered,
            candidate_digest,
            uploaded.asset_id,
            now,
            key_epoch,
        )
        self._commit_state(encrypted_state, healthy)
        return TimelinePublishResult(
            (
                TimelinePublishAction.ASSET_REPAIRED
                if was_repair
                else TimelinePublishAction.ASSET_REPLACED
            ),
            TimelinePublishStateName.HEALTHY,
            1,
            1,
            mutations,
            1,
            "FIXED_ASSET_REMOTE_RECOVERY_VERIFIED",
        )

    def _candidate_is_recoverable(
        self,
        asset: ReleaseAsset,
        ciphertext_sha256: str,
        plaintext_sha256: str,
    ) -> bool:
        try:
            ciphertext = self._download_verified_envelope(asset)
            if hashlib.sha256(ciphertext).hexdigest() != ciphertext_sha256:
                return False
            plaintext = self._crypto.decrypt(ciphertext)
        except Exception:
            return False
        return hashlib.sha256(plaintext).hexdigest() == plaintext_sha256

    def _transition_to_repair(
        self,
        release_id: int,
        previous: EncryptedTimelineState | None,
        rendered: RenderedTimeline,
        ciphertext_sha256: str,
        now: datetime,
        key_epoch: str,
        mutations: int,
        reason_code: str,
        *,
        cause: Exception,
    ) -> TimelinePublishResult:
        remaining = self._validated_assets(release_id)
        if remaining:
            try:
                self._remote.delete(remaining[0].asset_id)
            except Exception as exc:
                raise TimelinePublishError(
                    "unrecoverable Timeline Asset could not be removed"
                ) from exc
            mutations += 1
        if self._validated_assets(release_id):
            raise TimelinePublishError("Timeline repair could not establish zero Assets") from cause
        repair = TimelinePrivatePublishState(
            processed_snapshot_root=rendered.processed_snapshot_root,
            timeline_plaintext_sha256=rendered.timeline_plaintext_sha256,
            timeline_ciphertext_sha256=ciphertext_sha256,
            release_asset_id=None,
            publish_state=TimelinePublishStateName.TIMELINE_REPAIR_REQUIRED,
            verified_at_utc=now,
            key_epoch=key_epoch,
        )
        self._commit_state(previous, repair)
        return TimelinePublishResult(
            TimelinePublishAction.REPAIR_REQUIRED,
            TimelinePublishStateName.TIMELINE_REPAIR_REQUIRED,
            0,
            1,
            mutations,
            1,
            reason_code,
        )

    def _validated_assets(self, release_id: int) -> tuple[ReleaseAsset, ...]:
        assets = self._remote.list_assets(release_id)
        if len(assets) > 1 or any(item.name != LIVE_ASSET_NAME for item in assets):
            raise TimelinePublishError(
                "fixed live Release does not contain zero or one fixed Asset"
            )
        return assets

    def _decode_state(
        self,
        encrypted: EncryptedTimelineState | None,
    ) -> TimelinePrivatePublishState | None:
        if encrypted is None:
            return None
        try:
            plaintext = self._crypto.decrypt(encrypted.ciphertext)
            return TimelinePrivatePublishState.from_bytes(plaintext)
        except Exception as exc:
            raise TimelinePublishError(
                "encrypted private Timeline state is not recoverable"
            ) from exc

    def _same_state_is_healthy(
        self,
        state: TimelinePrivatePublishState,
        assets: tuple[ReleaseAsset, ...],
        snapshot_root: str,
    ) -> bool:
        if (
            state.publish_state is not TimelinePublishStateName.HEALTHY
            or state.processed_snapshot_root != snapshot_root
            or len(assets) != 1
            or state.release_asset_id != assets[0].asset_id
        ):
            return False
        ciphertext = self._download_verified_envelope(assets[0])
        if hashlib.sha256(ciphertext).hexdigest() != state.timeline_ciphertext_sha256:
            return False
        try:
            plaintext = self._crypto.decrypt(ciphertext)
        except Exception:
            return False
        return hashlib.sha256(plaintext).hexdigest() == state.timeline_plaintext_sha256

    def _download_verified_envelope(self, asset: ReleaseAsset) -> bytes:
        if asset.state != "uploaded" or asset.size <= 0:
            raise TimelinePublishError("current Timeline Asset is not uploaded")
        ciphertext = self._remote.download(asset.asset_id)
        if len(ciphertext) != asset.size or not is_age_envelope(ciphertext):
            raise TimelinePublishError("current Timeline Asset is not a valid age envelope")
        return ciphertext

    def _commit_state(
        self,
        previous: EncryptedTimelineState | None,
        state: TimelinePrivatePublishState,
    ) -> None:
        ciphertext = self._crypto.encrypt(state.to_bytes())
        if (
            not is_age_envelope(ciphertext)
            or len(ciphertext) > MAXIMUM_TIMELINE_STATE_CIPHERTEXT_BYTES
        ):
            raise TimelinePublishError("private Timeline state is not age encrypted")
        expected = previous.revision if previous is not None else None
        committed = self._state_store.compare_and_swap(expected, ciphertext)
        try:
            recovered = TimelinePrivatePublishState.from_bytes(
                self._crypto.decrypt(committed.ciphertext)
            )
        except Exception as exc:
            raise TimelinePublishError("committed Timeline state is not recoverable") from exc
        if recovered != state:
            raise TimelinePublishError("committed Timeline state differs from candidate")

    @staticmethod
    def _healthy_state(
        rendered: RenderedTimeline,
        ciphertext_sha256: str,
        asset_id: int,
        now: datetime,
        key_epoch: str,
    ) -> TimelinePrivatePublishState:
        return TimelinePrivatePublishState(
            processed_snapshot_root=rendered.processed_snapshot_root,
            timeline_plaintext_sha256=rendered.timeline_plaintext_sha256,
            timeline_ciphertext_sha256=ciphertext_sha256,
            release_asset_id=asset_id,
            publish_state=TimelinePublishStateName.HEALTHY,
            verified_at_utc=now,
            key_epoch=key_epoch,
        )


class MemoryTimelineReleaseRemote:
    """In-memory fixed Release with fault injection and maximum-count observation."""

    release_id = 501

    def __init__(self) -> None:
        self._assets: dict[int, tuple[ReleaseAsset, bytes]] = {}
        self._next_id = 1
        self.fail_next_upload = False
        self.raise_after_next_upload = False
        self.corrupt_next_upload_storage = False
        self.actions: list[str] = []
        self.maximum_observed_asset_count = 0

    def ensure_release(self) -> int:
        self.actions.append("ensure_release")
        return self.release_id

    def list_assets(self, release_id: int) -> tuple[ReleaseAsset, ...]:
        if release_id != self.release_id:
            raise TimelinePublishError("synthetic Release ID differs")
        self.maximum_observed_asset_count = max(
            self.maximum_observed_asset_count,
            len(self._assets),
        )
        return tuple(self._assets[key][0] for key in sorted(self._assets))

    def download(self, asset_id: int) -> bytes:
        self.actions.append("download")
        try:
            return bytes(self._assets[asset_id][1])
        except KeyError as exc:
            raise TimelinePublishError("synthetic Asset does not exist") from exc

    def delete(self, asset_id: int) -> None:
        self.actions.append("delete")
        if asset_id not in self._assets:
            raise TimelinePublishError("synthetic Asset does not exist")
        del self._assets[asset_id]

    def upload(self, release_id: int, name: str, ciphertext: bytes) -> ReleaseAsset:
        self.actions.append("upload")
        if self.fail_next_upload:
            self.fail_next_upload = False
            raise TimelinePublishError("synthetic upload failure")
        if (
            release_id != self.release_id
            or name != LIVE_ASSET_NAME
            or self._assets
            or not is_age_envelope(ciphertext)
        ):
            raise TimelinePublishError("synthetic upload violates the fixed Asset contract")
        asset = ReleaseAsset(self._next_id, name, "uploaded", len(ciphertext))
        stored = bytes(ciphertext)
        if self.corrupt_next_upload_storage:
            self.corrupt_next_upload_storage = False
            stored = b"x" + stored[1:]
        self._assets[asset.asset_id] = (asset, stored)
        self._next_id += 1
        self.maximum_observed_asset_count = max(self.maximum_observed_asset_count, 1)
        if self.raise_after_next_upload:
            self.raise_after_next_upload = False
            raise TimelinePublishError("synthetic response lost after upload")
        return asset

    def inject_asset_for_test(self, name: str, ciphertext: bytes) -> None:
        asset = ReleaseAsset(self._next_id, name, "uploaded", len(ciphertext))
        self._assets[asset.asset_id] = (asset, bytes(ciphertext))
        self._next_id += 1


class MemoryTimelineStateStore:
    def __init__(self) -> None:
        self._current: EncryptedTimelineState | None = None
        self.commit_calls = 0

    def read(self) -> EncryptedTimelineState | None:
        return self._current

    def compare_and_swap(
        self,
        expected_revision: str | None,
        ciphertext: bytes,
    ) -> EncryptedTimelineState:
        current_revision = self._current.revision if self._current is not None else None
        if current_revision != expected_revision or not is_age_envelope(ciphertext):
            raise TimelinePublishError("synthetic Timeline state CAS failed")
        self.commit_calls += 1
        revision = hashlib.sha1(
            str(self.commit_calls).encode("ascii") + b"\0" + ciphertext,
            usedforsecurity=False,
        ).hexdigest()
        self._current = EncryptedTimelineState(bytes(ciphertext), revision)
        return self._current


class GitHubTimelineReleaseRemote:
    """Guarded production-capable adapter for the one fixed private Release."""

    def __init__(
        self,
        guard: GitHubEndpointGuard,
        locator: RepositoryLocator,
        token: InstallationToken,
    ) -> None:
        self._guard = guard
        self._locator = locator
        self._token = token

    def ensure_release(self) -> int:
        for attempt in range(2):
            response = self._guard.send(
                HttpRequest(
                    "GET",
                    self._api(f"/releases/tags/{LIVE_RELEASE_TAG}"),
                    headers=self._headers("application/vnd.github+json"),
                )
            )
            if response.status == 200:
                return self._release_id(response.body)
            if response.status != 404 or attempt != 0:
                raise TimelinePublishError("fixed live Release resolution failed")
            created = self._guard.send(
                HttpRequest(
                    "POST",
                    self._api("/releases"),
                    headers=self._headers("application/vnd.github+json", json_body=True),
                    body=_canonical_json(
                        {
                            "draft": False,
                            "name": LIVE_RELEASE_TAG,
                            "prerelease": False,
                            "tag_name": LIVE_RELEASE_TAG,
                        }
                    ),
                )
            )
            if created.status == 201:
                return self._release_id(created.body)
            if created.status != 422:
                raise TimelinePublishError("fixed live Release creation failed")
        raise TimelinePublishError("fixed live Release resolution did not converge")

    @staticmethod
    def _release_id(payload: bytes) -> int:
        value = _decode_object(payload)
        release_id = value.get("id")
        if (
            type(release_id) is not int
            or release_id <= 0
            or value.get("tag_name") != LIVE_RELEASE_TAG
            or value.get("draft") is not False
            or value.get("prerelease") is not False
        ):
            raise TimelinePublishError("fixed live Release response is invalid")
        return release_id

    def list_assets(self, release_id: int) -> tuple[ReleaseAsset, ...]:
        response = self._guard.send(
            HttpRequest(
                "GET",
                self._api(f"/releases/{release_id}/assets"),
                headers=self._headers("application/vnd.github+json"),
            )
        )
        if response.status != 200:
            raise TimelinePublishError("fixed live Release Asset listing failed")
        value = _decode_array(response.body)
        return tuple(_parse_asset(item) for item in value)

    def download(self, asset_id: int) -> bytes:
        response = self._guard.send(
            HttpRequest(
                "GET",
                self._api(f"/releases/assets/{asset_id}"),
                headers=self._headers("application/octet-stream"),
            )
        )
        if response.status != 200 or not is_age_envelope(response.body):
            raise TimelinePublishError("fixed Timeline Asset download failed")
        return response.body

    def delete(self, asset_id: int) -> None:
        response = self._guard.send(
            HttpRequest(
                "DELETE",
                self._api(f"/releases/assets/{asset_id}"),
                headers=self._headers("application/vnd.github+json"),
            )
        )
        if response.status != 204:
            raise TimelinePublishError("fixed Timeline Asset deletion failed")

    def upload(self, release_id: int, name: str, ciphertext: bytes) -> ReleaseAsset:
        if name != LIVE_ASSET_NAME or not is_age_envelope(ciphertext):
            raise TimelinePublishError("Timeline upload candidate violates the fixed contract")
        response = self._guard.send(
            HttpRequest(
                "POST",
                self._upload(f"/releases/{release_id}/assets?name={LIVE_ASSET_NAME}"),
                headers=self._headers("application/vnd.github+json", octet_body=True),
                body=ciphertext,
            )
        )
        if response.status != 201:
            raise TimelinePublishError("fixed Timeline Asset upload failed")
        return _parse_asset(_decode_object(response.body))

    def _api(self, suffix: str) -> str:
        return GITHUB_API_ORIGIN + f"/repos/{self._locator.owner}/{self._locator.name}" + suffix

    def _upload(self, suffix: str) -> str:
        return GITHUB_UPLOAD_ORIGIN + f"/repos/{self._locator.owner}/{self._locator.name}" + suffix

    def _headers(
        self,
        accept: str,
        *,
        json_body: bool = False,
        octet_body: bool = False,
    ) -> tuple[tuple[str, str], ...]:
        if json_body and octet_body:
            raise TimelinePublishError("GitHub content type is ambiguous")
        try:
            token = self._token.value.reveal()
        except Exception as exc:
            raise GitHubBoundaryError("installation token is unavailable") from exc
        headers = [
            ("Accept", accept),
            ("Authorization", "Bearer " + token),
            ("X-GitHub-Api-Version", GITHUB_API_VERSION),
        ]
        if json_body:
            headers.append(("Content-Type", "application/json"))
        if octet_body:
            headers.append(("Content-Type", "application/octet-stream"))
        return tuple(headers)


class GitHubTimelineStateStore:
    """Encrypted mutable state at one exact path using GitHub Contents CAS."""

    def __init__(
        self,
        guard: GitHubEndpointGuard,
        locator: RepositoryLocator,
        token: InstallationToken,
    ) -> None:
        self._guard = guard
        self._locator = locator
        self._token = token

    def read(self) -> EncryptedTimelineState | None:
        response = self._guard.send(
            HttpRequest(
                "GET",
                content_url(self._locator, TIMELINE_STATE_PATH),
                headers=self._headers(),
            )
        )
        if response.status == 404:
            return None
        if response.status != 200:
            raise TimelinePublishError("encrypted Timeline state read failed")
        value = _decode_object(response.body)
        if value.get("encoding") != "base64":
            raise TimelinePublishError("encrypted Timeline state encoding is invalid")
        encoded = value.get("content")
        revision = value.get("sha")
        if not isinstance(encoded, str) or not isinstance(revision, str):
            raise TimelinePublishError("encrypted Timeline state response is invalid")
        try:
            ciphertext = base64.b64decode(encoded.replace("\n", ""), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TimelinePublishError("encrypted Timeline state base64 is invalid") from exc
        return EncryptedTimelineState(ciphertext, revision)

    def compare_and_swap(
        self,
        expected_revision: str | None,
        ciphertext: bytes,
    ) -> EncryptedTimelineState:
        if not is_age_envelope(ciphertext):
            raise TimelinePublishError("Timeline state store rejected plaintext")
        payload: dict[str, object] = {
            "content": base64.b64encode(ciphertext).decode("ascii"),
            "message": CONTENT_TIMELINE_STATE_MESSAGE,
        }
        if expected_revision is not None:
            payload["sha"] = expected_revision
        response = self._guard.send(
            HttpRequest(
                "PUT",
                content_url(self._locator, TIMELINE_STATE_PATH),
                headers=self._headers(json_body=True),
                body=_canonical_json(payload),
            )
        )
        if response.status not in {200, 201}:
            raise TimelinePublishError("encrypted Timeline state CAS failed")
        committed = self.read()
        if committed is None or committed.ciphertext != ciphertext:
            raise TimelinePublishError("encrypted Timeline state remote recovery failed")
        return committed

    def _headers(self, *, json_body: bool = False) -> tuple[tuple[str, str], ...]:
        try:
            token = self._token.value.reveal()
        except Exception as exc:
            raise GitHubBoundaryError("installation token is unavailable") from exc
        values = [
            ("Accept", "application/vnd.github+json"),
            ("Authorization", "Bearer " + token),
            ("X-GitHub-Api-Version", GITHUB_API_VERSION),
        ]
        if json_body:
            values.append(("Content-Type", "application/json"))
        return tuple(values)


def _parse_asset(value: object) -> ReleaseAsset:
    if not isinstance(value, dict):
        raise TimelinePublishError("Release Asset response is invalid")
    asset_id = value.get("id")
    name = value.get("name")
    state = value.get("state")
    size = value.get("size")
    if (
        type(asset_id) is not int
        or not isinstance(name, str)
        or not isinstance(state, str)
        or type(size) is not int
    ):
        raise TimelinePublishError("Release Asset response fields are invalid")
    return ReleaseAsset(asset_id, name, state, size)


def _decode_object(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimelinePublishError("GitHub response is invalid JSON") from exc
    if not isinstance(value, dict):
        raise TimelinePublishError("GitHub response is not an object")
    return cast(dict[str, object], value)


def _decode_array(payload: bytes) -> list[object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimelinePublishError("GitHub response is invalid JSON") from exc
    if not isinstance(value, list):
        raise TimelinePublishError("GitHub response is not an array")
    return cast(list[object], value)


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise TimelinePublishError("private Timeline state field is invalid")
    return item


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _require_utc(value: datetime) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise TimelinePublishError("Timeline timestamp must be UTC")
    return value


def _utc_text(value: datetime) -> str:
    return _require_utc(value).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimelinePublishError("private Timeline state timestamp is invalid") from exc
    return _require_utc(parsed)
