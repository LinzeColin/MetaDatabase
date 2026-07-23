"""Age-encrypted Gmail History checkpoint with strict private-repository CAS.

The checkpoint is the only cross-run discovery state.  Gmail message and thread identifiers
exist only in the encrypted payload and in ephemeral process memory; public results expose
counts only.  A successful commit is re-read, decrypted and compared before the caller may
consider the scheduled run complete.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, cast

from .age_stream import is_age_envelope
from .github_guard import (
    CONTENT_GMAIL_SYNC_STATE_MESSAGE,
    GITHUB_API_VERSION,
    GMAIL_SYNC_STATE_PATH,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    InstallationToken,
    RepositoryLocator,
    content_url,
)
from .gmail_discovery import MessageRef, SyncState
from .http_boundary import HttpRequest

_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PLAINTEXT_BYTES = 64 * 1024 * 1024
MAXIMUM_GMAIL_SYNC_CIPHERTEXT_BYTES = 65 * 1024 * 1024


class GmailSyncCheckpointError(RuntimeError):
    """The encrypted Gmail checkpoint is unsafe, stale or not remotely recoverable."""


class GmailSyncCrypto(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> bytes: ...


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedGmailSyncState:
    ciphertext: bytes = field(repr=False)
    revision: str

    def __post_init__(self) -> None:
        if not is_age_envelope(self.ciphertext) or _REVISION.fullmatch(self.revision) is None:
            raise GmailSyncCheckpointError("encrypted Gmail sync state is invalid")

    def __repr__(self) -> str:
        return "EncryptedGmailSyncState(ciphertext=<redacted>, revision=<redacted>)"


class GmailSyncStateStore(Protocol):
    def read(self) -> EncryptedGmailSyncState | None: ...

    def compare_and_swap(
        self,
        expected_revision: str | None,
        ciphertext: bytes,
    ) -> EncryptedGmailSyncState: ...


@dataclass(frozen=True, slots=True, repr=False)
class GmailRunCheckpoint:
    """History truth plus verified work that a bounded M3 run must replay."""

    sync_state: SyncState
    pending_verified_refs: tuple[MessageRef, ...]
    last_successful_run_date_sydney: date | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.sync_state, SyncState)
            or not isinstance(self.pending_verified_refs, tuple)
            or any(not isinstance(item, MessageRef) for item in self.pending_verified_refs)
            or (
                self.last_successful_run_date_sydney is not None
                and (
                    not isinstance(self.last_successful_run_date_sydney, date)
                    or isinstance(self.last_successful_run_date_sydney, datetime)
                )
            )
        ):
            raise GmailSyncCheckpointError("Gmail run checkpoint is invalid")
        known = {item.message_id: item.thread_id for item in self.sync_state.known_refs}
        pending_ids = [item.message_id for item in self.pending_verified_refs]
        if (
            pending_ids != sorted(pending_ids)
            or len(pending_ids) != len(set(pending_ids))
            or any(
                known.get(item.message_id) != item.thread_id for item in self.pending_verified_refs
            )
        ):
            raise GmailSyncCheckpointError("Gmail run checkpoint is invalid")

    def __repr__(self) -> str:
        return (
            "GmailRunCheckpoint(sync_state=<redacted>, pending_verified_refs=<redacted>, "
            f"pending_count={len(self.pending_verified_refs)}, "
            "last_successful_run_date_sydney=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecoveredGmailSyncCheckpoint:
    checkpoint: GmailRunCheckpoint
    revision: str
    ciphertext_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.checkpoint, GmailRunCheckpoint)
            or _REVISION.fullmatch(self.revision) is None
            or _SHA256.fullmatch(self.ciphertext_sha256) is None
        ):
            raise GmailSyncCheckpointError("recovered Gmail sync checkpoint is invalid")

    def __repr__(self) -> str:
        return (
            "RecoveredGmailSyncCheckpoint(state=<redacted>, revision=<redacted>, "
            "ciphertext_sha256=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class GmailSyncCheckpointCommitResult:
    checkpoint: RecoveredGmailSyncCheckpoint
    state_mutations: int
    remote_recovery_verified: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.checkpoint, RecoveredGmailSyncCheckpoint)
            or self.state_mutations not in {0, 1}
            or self.remote_recovery_verified is not True
        ):
            raise GmailSyncCheckpointError("Gmail sync checkpoint result is inconsistent")

    def __repr__(self) -> str:
        return (
            "GmailSyncCheckpointCommitResult(checkpoint=<redacted>, "
            f"state_mutations={self.state_mutations}, remote_recovery_verified=True)"
        )


class EncryptedGmailSyncCheckpoint:
    """Recover and CAS one canonical encrypted Gmail History checkpoint."""

    def __init__(self, store: GmailSyncStateStore, crypto: GmailSyncCrypto) -> None:
        self._store = store
        self._crypto = crypto

    def recover(self) -> RecoveredGmailSyncCheckpoint | None:
        encrypted = self._store.read()
        if encrypted is None:
            return None
        try:
            plaintext = self._crypto.decrypt(encrypted.ciphertext)
            checkpoint = _decode_checkpoint(plaintext)
        except Exception as exc:
            raise GmailSyncCheckpointError("Gmail sync checkpoint recovery failed") from exc
        return RecoveredGmailSyncCheckpoint(
            checkpoint,
            encrypted.revision,
            hashlib.sha256(encrypted.ciphertext).hexdigest(),
        )

    def commit(
        self,
        expected: RecoveredGmailSyncCheckpoint | None,
        checkpoint: GmailRunCheckpoint,
    ) -> GmailSyncCheckpointCommitResult:
        if not isinstance(checkpoint, GmailRunCheckpoint):
            raise GmailSyncCheckpointError("Gmail sync checkpoint input is invalid")
        if expected is not None and expected.checkpoint == checkpoint:
            current = self.recover()
            if current != expected:
                raise GmailSyncCheckpointError("Gmail sync checkpoint changed before no-op commit")
            return GmailSyncCheckpointCommitResult(current, 0, True)

        plaintext = _encode_checkpoint(checkpoint)
        try:
            ciphertext = self._crypto.encrypt(plaintext)
            if (
                not is_age_envelope(ciphertext)
                or len(ciphertext) > MAXIMUM_GMAIL_SYNC_CIPHERTEXT_BYTES
                or self._crypto.decrypt(ciphertext) != plaintext
            ):
                raise GmailSyncCheckpointError("Gmail sync checkpoint local round-trip failed")
        except GmailSyncCheckpointError:
            raise
        except Exception as exc:
            raise GmailSyncCheckpointError("Gmail sync checkpoint encryption failed") from exc
        committed = self._store.compare_and_swap(
            expected.revision if expected is not None else None,
            ciphertext,
        )
        recovered = self.recover()
        if (
            recovered is None
            or recovered.checkpoint != checkpoint
            or recovered.revision != committed.revision
            or recovered.ciphertext_sha256 != hashlib.sha256(ciphertext).hexdigest()
        ):
            raise GmailSyncCheckpointError("Gmail sync checkpoint remote recovery differs")
        return GmailSyncCheckpointCommitResult(recovered, 1, True)


class MemoryGmailSyncStateStore:
    """Synthetic remote retaining ciphertext only and enforcing strict CAS."""

    def __init__(self) -> None:
        self._current: EncryptedGmailSyncState | None = None
        self.commit_calls = 0
        self.read_calls = 0

    def read(self) -> EncryptedGmailSyncState | None:
        self.read_calls += 1
        return self._current

    def compare_and_swap(
        self,
        expected_revision: str | None,
        ciphertext: bytes,
    ) -> EncryptedGmailSyncState:
        current_revision = self._current.revision if self._current is not None else None
        if current_revision != expected_revision or not is_age_envelope(ciphertext):
            raise GmailSyncCheckpointError("synthetic Gmail sync state CAS failed")
        self.commit_calls += 1
        revision = hashlib.sha1(
            str(self.commit_calls).encode("ascii") + b"\0" + ciphertext,
            usedforsecurity=False,
        ).hexdigest()
        self._current = EncryptedGmailSyncState(bytes(ciphertext), revision)
        return self._current

    def ciphertext(self) -> bytes | None:
        return bytes(self._current.ciphertext) if self._current is not None else None


class GitHubGmailSyncStateStore:
    """Production-capable exact-path GitHub Contents CAS for encrypted sync state."""

    def __init__(
        self,
        guard: GitHubEndpointGuard,
        locator: RepositoryLocator,
        token: InstallationToken,
    ) -> None:
        self._guard = guard
        self._locator = locator
        self._token = token

    def read(self) -> EncryptedGmailSyncState | None:
        response = self._guard.send(
            HttpRequest(
                "GET",
                content_url(self._locator, GMAIL_SYNC_STATE_PATH),
                headers=self._headers(),
            )
        )
        if response.status == 404:
            return None
        if response.status != 200:
            raise GmailSyncCheckpointError("encrypted Gmail sync state read failed")
        try:
            value = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GmailSyncCheckpointError(
                "encrypted Gmail sync state response is invalid"
            ) from exc
        if not isinstance(value, dict) or value.get("encoding") != "base64":
            raise GmailSyncCheckpointError("encrypted Gmail sync state response is invalid")
        encoded = value.get("content")
        revision = value.get("sha")
        if not isinstance(encoded, str) or not isinstance(revision, str):
            raise GmailSyncCheckpointError("encrypted Gmail sync state response is invalid")
        compact = encoded.replace("\n", "")
        if any(character.isspace() for character in compact):
            raise GmailSyncCheckpointError("encrypted Gmail sync state base64 is invalid")
        try:
            ciphertext = base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise GmailSyncCheckpointError("encrypted Gmail sync state base64 is invalid") from exc
        return EncryptedGmailSyncState(ciphertext, revision)

    def compare_and_swap(
        self,
        expected_revision: str | None,
        ciphertext: bytes,
    ) -> EncryptedGmailSyncState:
        if not is_age_envelope(ciphertext):
            raise GmailSyncCheckpointError("Gmail sync state store rejected plaintext")
        payload: dict[str, object] = {
            "content": base64.b64encode(ciphertext).decode("ascii"),
            "message": CONTENT_GMAIL_SYNC_STATE_MESSAGE,
        }
        if expected_revision is not None:
            payload["sha"] = expected_revision
        response = self._guard.send(
            HttpRequest(
                "PUT",
                content_url(self._locator, GMAIL_SYNC_STATE_PATH),
                headers=self._headers(json_body=True),
                body=_canonical_json(payload),
            )
        )
        if response.status not in {200, 201}:
            raise GmailSyncCheckpointError("encrypted Gmail sync state CAS failed")
        committed = self.read()
        if committed is None or committed.ciphertext != ciphertext:
            raise GmailSyncCheckpointError("encrypted Gmail sync state remote read differs")
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


def _encode_checkpoint(checkpoint: GmailRunCheckpoint) -> bytes:
    state = checkpoint.sync_state
    payload = _canonical_json(
        {
            "schema_version": "moomooau.gmail-run-checkpoint.v2",
            "history_id": state.history_id,
            "known_refs": [
                {"message_id": item.message_id, "thread_id": item.thread_id}
                for item in state.known_refs
            ],
            "last_successful_run_date_sydney": (
                checkpoint.last_successful_run_date_sydney.isoformat()
                if checkpoint.last_successful_run_date_sydney is not None
                else None
            ),
            "pending_verified_refs": [
                {"message_id": item.message_id, "thread_id": item.thread_id}
                for item in checkpoint.pending_verified_refs
            ],
        }
    )
    if len(payload) > _MAX_PLAINTEXT_BYTES:
        raise GmailSyncCheckpointError("Gmail sync state exceeds the safe limit")
    return payload


def _decode_checkpoint(payload: bytes) -> GmailRunCheckpoint:
    if not payload or len(payload) > _MAX_PLAINTEXT_BYTES:
        raise GmailSyncCheckpointError("Gmail sync state exceeds the safe limit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GmailSyncCheckpointError("Gmail sync state is not valid JSON") from exc
    if not isinstance(value, dict):
        raise GmailSyncCheckpointError("Gmail sync state schema is invalid")
    schema_version = value.get("schema_version")
    common = {"schema_version", "history_id", "known_refs", "pending_verified_refs"}
    if schema_version == "moomooau.gmail-run-checkpoint.v1":
        if set(value) != common:
            raise GmailSyncCheckpointError("Gmail sync state schema is invalid")
        last_successful_run_date_sydney = None
    elif schema_version == "moomooau.gmail-run-checkpoint.v2":
        if set(value) != common | {"last_successful_run_date_sydney"}:
            raise GmailSyncCheckpointError("Gmail sync state schema is invalid")
        raw_date = value.get("last_successful_run_date_sydney")
        if raw_date is None:
            last_successful_run_date_sydney = None
        elif isinstance(raw_date, str):
            try:
                last_successful_run_date_sydney = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise GmailSyncCheckpointError(
                    "Gmail run checkpoint Sydney date is invalid"
                ) from exc
            if last_successful_run_date_sydney.isoformat() != raw_date:
                raise GmailSyncCheckpointError("Gmail run checkpoint Sydney date is invalid")
        else:
            raise GmailSyncCheckpointError("Gmail run checkpoint Sydney date is invalid")
    else:
        raise GmailSyncCheckpointError("Gmail sync state schema is invalid")
    raw_history = value.get("history_id")
    raw_refs = value.get("known_refs")
    raw_pending = value.get("pending_verified_refs")
    if raw_history is not None and not isinstance(raw_history, str):
        raise GmailSyncCheckpointError("Gmail sync History ID is invalid")
    if not isinstance(raw_refs, list) or not isinstance(raw_pending, list):
        raise GmailSyncCheckpointError("Gmail sync refs are invalid")
    refs = _decode_refs(raw_refs)
    pending = _decode_refs(raw_pending)
    checkpoint = GmailRunCheckpoint(
        SyncState(raw_history, refs),
        pending,
        last_successful_run_date_sydney,
    )
    canonical = (
        _encode_legacy_checkpoint(checkpoint)
        if schema_version == "moomooau.gmail-run-checkpoint.v1"
        else _encode_checkpoint(checkpoint)
    )
    if canonical != payload:
        raise GmailSyncCheckpointError("Gmail run checkpoint is not canonical")
    return checkpoint


def _encode_legacy_checkpoint(checkpoint: GmailRunCheckpoint) -> bytes:
    if checkpoint.last_successful_run_date_sydney is not None:
        raise GmailSyncCheckpointError("legacy Gmail checkpoint cannot contain a Sydney date")
    state = checkpoint.sync_state
    return _canonical_json(
        {
            "schema_version": "moomooau.gmail-run-checkpoint.v1",
            "history_id": state.history_id,
            "known_refs": [
                {"message_id": item.message_id, "thread_id": item.thread_id}
                for item in state.known_refs
            ],
            "pending_verified_refs": [
                {"message_id": item.message_id, "thread_id": item.thread_id}
                for item in checkpoint.pending_verified_refs
            ],
        }
    )


def _decode_refs(raw_refs: list[object]) -> tuple[MessageRef, ...]:
    refs: list[MessageRef] = []
    for raw in raw_refs:
        if not isinstance(raw, dict) or set(raw) != {"message_id", "thread_id"}:
            raise GmailSyncCheckpointError("Gmail sync ref schema is invalid")
        item = cast(dict[str, object], raw)
        message_id = item.get("message_id")
        thread_id = item.get("thread_id")
        if not isinstance(message_id, str) or not isinstance(thread_id, str):
            raise GmailSyncCheckpointError("Gmail sync ref value is invalid")
        refs.append(MessageRef(message_id, thread_id))
    return tuple(refs)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
