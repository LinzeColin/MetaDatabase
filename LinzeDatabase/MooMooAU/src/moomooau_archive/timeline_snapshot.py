"""Age-only committed Timeline facts and deterministic Processed snapshot recovery.

The live Timeline publisher must never trust a caller-supplied root or in-memory event list.
This module binds every Timeline Event to the encrypted current Processed pointer for the same
source, persists versioned JSONL facts plus one append-only encrypted manifest, and re-fetches
and decrypts that manifest before issuing an in-process recovery proof.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, cast

from .age_stream import OfficialAgeStream, is_age_envelope
from .processed_commit import CurrentProcessedPointer, ProcessedCiphertextStore
from .timeline_event import TimelineEvent

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_EVENT_PATH = re.compile(
    r"^MooMooAU/Processed/timeline_events/v1/[0-9a-f]{64}/[0-9a-f]{64}\.jsonl\.age$"
)
_MANIFEST_PATH = re.compile(r"^MooMooAU/Manifests/timeline/[0-9a-f]{64}\.json\.age$")
_MAX_FACTS = 5000
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_RECOVERY_SENTINEL = object()


class TimelineSnapshotError(RuntimeError):
    """A committed Timeline snapshot is invalid or not remotely recoverable."""


class TimelineSnapshotObjectRole(StrEnum):
    EVENT = "EVENT"
    MANIFEST = "MANIFEST"


@dataclass(frozen=True, slots=True, repr=False)
class TimelineSnapshotFact:
    """One current Processed pointer and its deterministic Timeline Event."""

    current_pointer: CurrentProcessedPointer
    event: TimelineEvent

    def __post_init__(self) -> None:
        if (
            not isinstance(self.current_pointer, CurrentProcessedPointer)
            or not isinstance(self.event, TimelineEvent)
            or self.current_pointer.source_id != self.event.source_id
        ):
            raise TimelineSnapshotError("Timeline fact is not bound to one current source")

    def __repr__(self) -> str:
        return (
            "TimelineSnapshotFact(source_id=<redacted>, current_pointer=<redacted>, "
            "event=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class PrivateTimelineSnapshotObject:
    relative_path: str
    role: TimelineSnapshotObjectRole
    plaintext_sha256: str
    ciphertext_sha256: str
    ciphertext: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.role, TimelineSnapshotObjectRole):
            raise TimelineSnapshotError("private Timeline snapshot role is invalid")
        path_valid = (
            _EVENT_PATH.fullmatch(self.relative_path) is not None
            if self.role is TimelineSnapshotObjectRole.EVENT
            else _MANIFEST_PATH.fullmatch(self.relative_path) is not None
        )
        if (
            not path_valid
            or _SHA256.fullmatch(self.plaintext_sha256) is None
            or _SHA256.fullmatch(self.ciphertext_sha256) is None
            or hashlib.sha256(self.ciphertext).hexdigest() != self.ciphertext_sha256
            or not is_age_envelope(self.ciphertext)
        ):
            raise TimelineSnapshotError("private Timeline snapshot object is invalid")

    def __repr__(self) -> str:
        return (
            "PrivateTimelineSnapshotObject(relative_path=<redacted>, "
            f"role={self.role.value!r}, plaintext_sha256=<redacted>, "
            "ciphertext_sha256=<redacted>, ciphertext=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class TimelineSnapshotPlan:
    processed_snapshot_root: str
    key_epoch: str
    facts: tuple[TimelineSnapshotFact, ...]
    objects: tuple[PrivateTimelineSnapshotObject, ...]

    def __post_init__(self) -> None:
        source_ids = [item.event.source_id for item in self.facts]
        event_objects = [
            item for item in self.objects if item.role is TimelineSnapshotObjectRole.EVENT
        ]
        manifest_objects = [
            item for item in self.objects if item.role is TimelineSnapshotObjectRole.MANIFEST
        ]
        if (
            _SHA256.fullmatch(self.processed_snapshot_root) is None
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or not self.facts
            or len(self.facts) > _MAX_FACTS
            or source_ids != sorted(source_ids)
            or len(source_ids) != len(set(source_ids))
            or self.processed_snapshot_root != _snapshot_root(self.facts)
            or len(event_objects) != len(self.facts)
            or len(manifest_objects) != 1
            or self.objects[-1] is not manifest_objects[0]
            or manifest_objects[0].relative_path != _manifest_path(self.processed_snapshot_root)
            or [item.relative_path for item in event_objects]
            != [_event_path(fact) for fact in self.facts]
            or len({item.relative_path for item in self.objects}) != len(self.objects)
        ):
            raise TimelineSnapshotError("Timeline snapshot plan is invalid")

    def __repr__(self) -> str:
        return (
            "TimelineSnapshotPlan(processed_snapshot_root=<redacted>, "
            "key_epoch=<redacted>, "
            f"fact_count={len(self.facts)}, object_count={len(self.objects)})"
        )


class TimelineSnapshotPlanner:
    """Create deterministic logical facts and randomized age ciphertext in memory."""

    def __init__(self, age: OfficialAgeStream, recipient: str) -> None:
        self._age = age
        self._recipient = recipient

    def plan(
        self,
        facts: tuple[TimelineSnapshotFact, ...],
        *,
        key_epoch: str,
    ) -> TimelineSnapshotPlan:
        ordered = tuple(sorted(facts, key=lambda item: item.event.source_id))
        if (
            _KEY_EPOCH.fullmatch(key_epoch) is None
            or not ordered
            or len(ordered) > _MAX_FACTS
            or len({item.event.source_id for item in ordered}) != len(ordered)
        ):
            raise TimelineSnapshotError("Timeline snapshot inputs are invalid")
        root = _snapshot_root(ordered)
        objects: list[PrivateTimelineSnapshotObject] = []
        manifest_facts: list[dict[str, str]] = []
        for fact in ordered:
            event_plaintext = _event_plaintext(fact.event)
            event_path = _event_path(fact)
            objects.append(
                self._encrypt(event_path, TimelineSnapshotObjectRole.EVENT, event_plaintext)
            )
            pointer_bytes = fact.current_pointer.to_bytes()
            manifest_facts.append(
                {
                    "source_id": fact.event.source_id,
                    "current_pointer_base64": base64.b64encode(pointer_bytes).decode("ascii"),
                    "current_pointer_sha256": hashlib.sha256(pointer_bytes).hexdigest(),
                    "timeline_event_path": event_path,
                    "timeline_event_plaintext_sha256": hashlib.sha256(event_plaintext).hexdigest(),
                }
            )
        manifest = _canonical_json(
            {
                "schema_version": "moomooau.timeline-snapshot-manifest.v1",
                "processed_snapshot_root": root,
                "key_epoch": key_epoch,
                "facts": manifest_facts,
            }
        )
        objects.append(
            self._encrypt(
                _manifest_path(root),
                TimelineSnapshotObjectRole.MANIFEST,
                manifest,
            )
        )
        return TimelineSnapshotPlan(root, key_epoch, ordered, tuple(objects))

    def _encrypt(
        self,
        relative_path: str,
        role: TimelineSnapshotObjectRole,
        plaintext: bytes,
    ) -> PrivateTimelineSnapshotObject:
        source = io.BytesIO(plaintext)
        sink = io.BytesIO()
        self._age.encrypt_stream(self._recipient, source, sink)
        ciphertext = sink.getvalue()
        return PrivateTimelineSnapshotObject(
            relative_path,
            role,
            hashlib.sha256(plaintext).hexdigest(),
            hashlib.sha256(ciphertext).hexdigest(),
            ciphertext,
        )


@dataclass(frozen=True, slots=True)
class TimelineSnapshotCommitResult:
    created_count: int
    existing_count: int
    object_count: int
    remote_recovery_verified: bool = False

    def __post_init__(self) -> None:
        if (
            any(
                type(item) is not int or item < 0
                for item in (self.created_count, self.existing_count, self.object_count)
            )
            or self.created_count + self.existing_count != self.object_count
            or type(self.remote_recovery_verified) is not bool
            or self.remote_recovery_verified
        ):
            raise TimelineSnapshotError("Timeline snapshot commit result is invalid")


class TimelineSnapshotCommitSaga:
    """Append encrypted facts and manifest without mutating Processed current pointers."""

    def __init__(self, store: ProcessedCiphertextStore) -> None:
        self._store = store

    def commit(self, plan: TimelineSnapshotPlan) -> TimelineSnapshotCommitResult:
        created = 0
        existing = 0
        for item in plan.objects:
            remote = self._store.fetch_immutable(item.relative_path)
            if remote is not None:
                if not is_age_envelope(remote):
                    raise TimelineSnapshotError(
                        "existing Timeline snapshot object is not age encrypted"
                    )
                existing += 1
                continue
            if self._store.append_immutable(item.relative_path, item.ciphertext):
                created += 1
                continue
            raced = self._store.fetch_immutable(item.relative_path)
            if raced is None or not is_age_envelope(raced):
                raise TimelineSnapshotError("Timeline snapshot append did not converge")
            existing += 1
        return TimelineSnapshotCommitResult(created, existing, len(plan.objects))


class TimelineSnapshotDecryptor(Protocol):
    def decrypt(self, ciphertext: bytes) -> bytes: ...


@dataclass(frozen=True, slots=True, repr=False)
class TimelineSnapshotRecoveryProof:
    processed_snapshot_root: str
    key_epoch: str
    facts: tuple[TimelineSnapshotFact, ...]
    recovered_object_count: int
    manifest_plaintext_sha256: str
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._sentinel is not _RECOVERY_SENTINEL
            or _SHA256.fullmatch(self.processed_snapshot_root) is None
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or not self.facts
            or self.processed_snapshot_root != _snapshot_root(self.facts)
            or self.recovered_object_count != len(self.facts) + 1
            or _SHA256.fullmatch(self.manifest_plaintext_sha256) is None
        ):
            raise TimelineSnapshotError("Timeline snapshot recovery proof is invalid")

    def __repr__(self) -> str:
        return (
            "TimelineSnapshotRecoveryProof(processed_snapshot_root=<redacted>, "
            "key_epoch=<redacted>, "
            f"fact_count={len(self.facts)}, recovered_object_count={self.recovered_object_count})"
        )


class TimelineSnapshotRecoveryGate:
    """Recover an append-only manifest and every selected Timeline Event from remote."""

    def __init__(
        self,
        store: ProcessedCiphertextStore,
        decryptor: TimelineSnapshotDecryptor,
    ) -> None:
        self._store = store
        self._decryptor = decryptor

    def verify(self, plan: TimelineSnapshotPlan) -> TimelineSnapshotRecoveryProof:
        proof = self.recover_root(plan.processed_snapshot_root)
        manifest = plan.objects[-1]
        if (
            proof.key_epoch != plan.key_epoch
            or proof.facts != plan.facts
            or proof.manifest_plaintext_sha256 != manifest.plaintext_sha256
        ):
            raise TimelineSnapshotError("remote Timeline snapshot differs from the plan")
        return proof

    def recover_root(self, processed_snapshot_root: str) -> TimelineSnapshotRecoveryProof:
        if _SHA256.fullmatch(processed_snapshot_root) is None:
            raise TimelineSnapshotError("Timeline snapshot root is invalid")
        manifest_plaintext = self._recover(_manifest_path(processed_snapshot_root))
        if len(manifest_plaintext) > _MAX_MANIFEST_BYTES:
            raise TimelineSnapshotError("Timeline snapshot manifest exceeds the safe limit")
        value = _decode_object(manifest_plaintext)
        if _canonical_json(value) != manifest_plaintext:
            raise TimelineSnapshotError("Timeline snapshot manifest is not canonical")
        required = {"schema_version", "processed_snapshot_root", "key_epoch", "facts"}
        raw_facts = value.get("facts")
        if (
            set(value) != required
            or value.get("schema_version") != "moomooau.timeline-snapshot-manifest.v1"
            or value.get("processed_snapshot_root") != processed_snapshot_root
            or not isinstance(raw_facts, list)
            or not 1 <= len(raw_facts) <= _MAX_FACTS
        ):
            raise TimelineSnapshotError("Timeline snapshot manifest schema is invalid")
        facts: list[TimelineSnapshotFact] = []
        prior_source: str | None = None
        for raw_fact in raw_facts:
            fact = self._recover_fact(raw_fact)
            if prior_source is not None and fact.event.source_id <= prior_source:
                raise TimelineSnapshotError("Timeline snapshot facts are not uniquely ordered")
            prior_source = fact.event.source_id
            facts.append(fact)
        ordered = tuple(facts)
        if _snapshot_root(ordered) != processed_snapshot_root:
            raise TimelineSnapshotError("Timeline snapshot root differs after recovery")
        return TimelineSnapshotRecoveryProof(
            processed_snapshot_root,
            _required_string(value, "key_epoch"),
            ordered,
            len(ordered) + 1,
            hashlib.sha256(manifest_plaintext).hexdigest(),
            _RECOVERY_SENTINEL,
        )

    def _recover_fact(self, raw: object) -> TimelineSnapshotFact:
        if not isinstance(raw, dict):
            raise TimelineSnapshotError("Timeline snapshot fact is invalid")
        value = cast(dict[str, object], raw)
        required = {
            "source_id",
            "current_pointer_base64",
            "current_pointer_sha256",
            "timeline_event_path",
            "timeline_event_plaintext_sha256",
        }
        if set(value) != required:
            raise TimelineSnapshotError("Timeline snapshot fact schema is invalid")
        source_id = _required_string(value, "source_id")
        pointer_encoded = _required_string(value, "current_pointer_base64")
        try:
            pointer_bytes = base64.b64decode(pointer_encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TimelineSnapshotError("Timeline current pointer encoding is invalid") from exc
        if hashlib.sha256(pointer_bytes).hexdigest() != _required_string(
            value, "current_pointer_sha256"
        ):
            raise TimelineSnapshotError("Timeline current pointer digest differs")
        try:
            pointer = CurrentProcessedPointer.from_bytes(pointer_bytes)
        except Exception as exc:
            raise TimelineSnapshotError("Timeline current pointer is invalid") from exc
        event_path = _required_string(value, "timeline_event_path")
        if _EVENT_PATH.fullmatch(event_path) is None:
            raise TimelineSnapshotError("Timeline Event path is invalid")
        event_plaintext = self._recover(event_path)
        if hashlib.sha256(event_plaintext).hexdigest() != _required_string(
            value, "timeline_event_plaintext_sha256"
        ) or not event_plaintext.endswith(b"\n"):
            raise TimelineSnapshotError("Timeline Event plaintext digest differs")
        try:
            event = TimelineEvent.from_bytes(event_plaintext[:-1])
        except Exception as exc:
            raise TimelineSnapshotError("Timeline Event recovery failed") from exc
        fact = TimelineSnapshotFact(pointer, event)
        if source_id != event.source_id or event_path != _event_path(fact):
            raise TimelineSnapshotError("Timeline snapshot fact identity differs")
        return fact

    def _recover(self, relative_path: str) -> bytes:
        remote = self._store.fetch_immutable(relative_path)
        if remote is None or not is_age_envelope(remote):
            raise TimelineSnapshotError("remote Timeline snapshot ciphertext is unavailable")
        try:
            return self._decryptor.decrypt(remote)
        except Exception as exc:
            raise TimelineSnapshotError("remote Timeline snapshot decryption failed") from exc


def _event_plaintext(event: TimelineEvent) -> bytes:
    return event.canonical_bytes() + b"\n"


def _event_path(fact: TimelineSnapshotFact) -> str:
    digest = hashlib.sha256(_event_plaintext(fact.event)).hexdigest()
    return f"MooMooAU/Processed/timeline_events/v1/{fact.event.source_id}/{digest}.jsonl.age"


def _manifest_path(processed_snapshot_root: str) -> str:
    return f"MooMooAU/Manifests/timeline/{processed_snapshot_root}.json.age"


def _snapshot_root(facts: tuple[TimelineSnapshotFact, ...]) -> str:
    descriptors = [
        {
            "source_id": fact.event.source_id,
            "current_pointer_sha256": hashlib.sha256(fact.current_pointer.to_bytes()).hexdigest(),
            "timeline_event_plaintext_sha256": hashlib.sha256(
                _event_plaintext(fact.event)
            ).hexdigest(),
        }
        for fact in facts
    ]
    return hashlib.sha256(
        _canonical_json(
            {
                "schema_version": "moomooau.timeline-snapshot-root.v1",
                "facts": descriptors,
            }
        )
    ).hexdigest()


def _decode_object(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimelineSnapshotError("Timeline snapshot JSON is invalid") from exc
    if not isinstance(value, dict):
        raise TimelineSnapshotError("Timeline snapshot JSON must be an object")
    return cast(dict[str, object], value)


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise TimelineSnapshotError("Timeline snapshot string field is invalid")
    return item


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TimelineSnapshotError("Timeline snapshot value is not canonical JSON") from exc
