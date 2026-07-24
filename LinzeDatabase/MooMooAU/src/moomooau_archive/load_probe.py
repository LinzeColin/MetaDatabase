"""Streaming synthetic load probes and a concurrency-safe logical object index."""

from __future__ import annotations

import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OBJECT_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class LoadProbeError(RuntimeError):
    pass


class UpsertResult(StrEnum):
    CREATED = "CREATED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True, slots=True)
class SyntheticLoadProfile:
    message_count: int
    attachment_count: int
    concurrency: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value <= 0
            for value in (self.message_count, self.attachment_count, self.concurrency)
        ):
            raise LoadProbeError("load profile values must be positive integers")
        if self.concurrency > 64:
            raise LoadProbeError("load concurrency exceeds the bounded worker limit")


@dataclass(frozen=True, slots=True)
class SyntheticLoadResult:
    message_count: int
    attachment_count: int
    batches: int
    maximum_batch_size: int
    stream_root: str
    logical_object_count: int
    created_count: int
    unchanged_count: int
    upsert_calls: int
    configured_concurrency: int


def run_streaming_load(
    profile: SyntheticLoadProfile,
    *,
    batch_size: int = 500,
) -> SyntheticLoadResult:
    """Stream real content-identity upserts through bounded concurrent batches.

    Each logical message and attachment is submitted twice to the thread-safe index.
    The concurrency race must converge to one created object plus one unchanged retry.
    """

    if type(batch_size) is not int or not 0 < batch_size <= 500:
        raise LoadProbeError("batch size must be an integer from 1 through 500")
    index = LogicalObjectIndex()
    remaining_attachments = profile.attachment_count
    batches = 0
    maximum_batch = 0
    created = 0
    unchanged = 0
    with ThreadPoolExecutor(
        max_workers=profile.concurrency,
        thread_name_prefix="moomoo-load",
    ) as executor:
        for start in range(0, profile.message_count, batch_size):
            current = min(batch_size, profile.message_count - start)
            maximum_batch = max(maximum_batch, current)
            batches += 1
            batch: list[tuple[int, int]] = []
            for offset in range(current):
                ordinal = start + offset
                messages_left = profile.message_count - ordinal
                attached = (remaining_attachments + messages_left - 1) // messages_left
                remaining_attachments -= attached
                batch.append((ordinal, attached))
            duplicate_race = tuple(item for item in batch for _retry in range(2))
            for created_now, unchanged_now in executor.map(
                lambda item: _upsert_load_item(index, *item),
                duplicate_race,
            ):
                created += created_now
                unchanged += unchanged_now
    if remaining_attachments != 0:
        raise LoadProbeError("streaming attachment allocation did not converge")
    expected_objects = profile.message_count + profile.attachment_count
    if (
        index.object_count != expected_objects
        or created != expected_objects
        or unchanged != expected_objects
        or index.calls != expected_objects * 2
    ):
        raise LoadProbeError("concurrent content-identity convergence failed")
    return SyntheticLoadResult(
        profile.message_count,
        profile.attachment_count,
        batches,
        maximum_batch,
        index.merkle_root(),
        index.object_count,
        created,
        unchanged,
        index.calls,
        profile.concurrency,
    )


def _upsert_load_item(index: LogicalObjectIndex, ordinal: int, attachments: int) -> tuple[int, int]:
    created = 0
    unchanged = 0
    identities = [(f"message-{ordinal:09d}", f"message:{ordinal}")]
    identities.extend(
        (f"attachment-{ordinal:09d}-{attachment:04d}", f"attachment:{ordinal}:{attachment}")
        for attachment in range(attachments)
    )
    for object_id, seed in identities:
        digest = hashlib.sha256(seed.encode("ascii")).hexdigest()
        if index.upsert(object_id, digest) is UpsertResult.CREATED:
            created += 1
        else:
            unchanged += 1
    return created, unchanged


class LogicalObjectIndex:
    """Converge concurrent retries by stable content identity, never ciphertext equality."""

    def __init__(self) -> None:
        self._objects: dict[str, str] = {}
        self._lock = threading.Lock()
        self._calls = 0

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls

    @property
    def object_count(self) -> int:
        with self._lock:
            return len(self._objects)

    def upsert(self, object_id: str, plaintext_sha256: str) -> UpsertResult:
        if _OBJECT_ID.fullmatch(object_id) is None or _SHA256.fullmatch(plaintext_sha256) is None:
            raise LoadProbeError("logical object identity is invalid")
        with self._lock:
            self._calls += 1
            current = self._objects.get(object_id)
            if current is None:
                self._objects[object_id] = plaintext_sha256
                return UpsertResult.CREATED
            if current != plaintext_sha256:
                raise LoadProbeError("logical object content conflict requires reconciliation")
            return UpsertResult.UNCHANGED

    def merkle_root(self) -> str:
        with self._lock:
            digest = hashlib.sha256()
            for object_id, plaintext_sha256 in sorted(self._objects.items()):
                digest.update(object_id.encode("ascii") + b"\0" + plaintext_sha256.encode("ascii"))
            return digest.hexdigest()


def partition_key(recorded_date: date) -> str:
    """Use the frozen shallow year/month partition for immutable private objects."""

    if type(recorded_date) is not date:
        raise LoadProbeError("partition date must be a date")
    return f"{recorded_date.year:04d}/{recorded_date.month:02d}"
