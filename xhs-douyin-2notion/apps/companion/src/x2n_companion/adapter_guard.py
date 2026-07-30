"""Cross-process Adapter mutex, low-frequency gate and deletion protection."""

from __future__ import annotations

import fcntl
import json
import math
import os
import stat
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from x2n_contracts import ErrorCode

from .runtime import PROFILE_PLATFORMS, RuntimePaths, X2NRuntimeError, _atomic_private_json


TASK_ID = "TSK.x2n.adapters.001"
POLICY_ID = "POLICY.X2N.ADAPTER-RUNTIME.001"
MUTEX_NAME = "adapter-runtime.lock"
RATE_STATE_NAME = "adapter-rate-state.json"
MINIMUM_BATCH_START_INTERVAL_SECONDS = 30.0
MINIMUM_ITEM_OBSERVATION_INTERVAL_SECONDS = 3.0

BatchOutcome = Literal[
    "auth_expired",
    "http_error",
    "platform_changed",
    "empty_response",
    "partial_scan",
    "complete_success",
]

NON_AUTHORITATIVE_OUTCOMES = {
    "auth_expired",
    "http_error",
    "platform_changed",
    "empty_response",
    "partial_scan",
}


def _validate_platform(platform: str) -> str:
    if platform not in PROFILE_PLATFORMS:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Adapter platform is unsupported")
    return platform


def _validate_time(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Adapter rate time is invalid")
    return float(value)


@dataclass(frozen=True)
class AdapterLease:
    """An opaque logical lease; it never exposes the lock or Profile path."""

    platform: str
    _gate: "AdapterExecutionGate"

    def permit_item_observation(self, *, now: float | None = None) -> dict[str, object]:
        return self._gate._permit_item(self.platform, time.time() if now is None else now)

    def safe_dict(self) -> dict[str, object]:
        return {
            "automatic_retry": False,
            "max_concurrent_adapters": 1,
            "mutex_acquired": True,
            "platform": self.platform,
            "policy_id": POLICY_ID,
            "private_path_emitted": False,
        }


class AdapterExecutionGate:
    """Serialize all adapters and persist a path-free durable rate receipt."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        batch_interval_seconds: float = MINIMUM_BATCH_START_INTERVAL_SECONDS,
        item_interval_seconds: float = MINIMUM_ITEM_OBSERVATION_INTERVAL_SECONDS,
    ) -> None:
        if batch_interval_seconds < MINIMUM_BATCH_START_INTERVAL_SECONDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter batch interval cannot be reduced")
        if item_interval_seconds < MINIMUM_ITEM_OBSERVATION_INTERVAL_SECONDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter item interval cannot be reduced")
        self.paths = paths
        self.batch_interval_seconds = float(batch_interval_seconds)
        self.item_interval_seconds = float(item_interval_seconds)
        self.lock_path = paths.checkpoints_directory / MUTEX_NAME
        self.state_path = paths.checkpoints_directory / RATE_STATE_NAME
        self._active_descriptor: int | None = None

    def _open_lock(self) -> int:
        if self.lock_path.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter mutex destination is unsafe")
        existed = self.lock_path.exists()
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
        except OSError as error:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter mutex destination is unsafe") from error
        metadata = os.fstat(descriptor)
        if not existed:
            self.lock_path.chmod(0o600)
            metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
        ):
            os.close(descriptor)
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter mutex is not owner-only")
        return descriptor

    def _load_state(self) -> dict[str, dict[str, float]]:
        if not self.state_path.exists():
            return {}
        if self.state_path.is_symlink() or not self.state_path.is_file():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter rate state is unsafe")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(self.state_path, flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.getuid()
                or metadata.st_size > 65_536
            ):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter rate state is not owner-only")
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                descriptor = -1
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Adapter rate state is invalid") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if not isinstance(payload, dict) or set(payload) != {"platforms", "schema_version"}:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Adapter rate state is invalid")
        platforms = payload.get("platforms")
        if payload.get("schema_version") != "1.0" or not isinstance(platforms, dict):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Adapter rate state is invalid")
        normalized: dict[str, dict[str, float]] = {}
        for platform, row in platforms.items():
            if platform not in PROFILE_PLATFORMS or not isinstance(row, dict):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Adapter rate state is invalid")
            if not set(row).issubset({"last_batch_start", "last_item_observation"}):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Adapter rate state is invalid")
            normalized[platform] = {key: _validate_time(value) for key, value in row.items()}
        return normalized

    def _write_state(self, state: dict[str, dict[str, float]]) -> None:
        _atomic_private_json(self.state_path, {"platforms": state, "schema_version": "1.0"})

    def _enforce_interval(self, *, previous: float | None, current: float, interval: float) -> None:
        if previous is not None and current < previous:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Adapter rate clock moved backwards")
        if previous is not None and current - previous < interval:
            raise X2NRuntimeError(ErrorCode.RATE_LIMITED, "Adapter low-frequency policy requires a later retry")

    @contextmanager
    def acquire(self, platform: str, *, now: float | None = None) -> Iterator[AdapterLease]:
        platform = _validate_platform(platform)
        current = _validate_time(time.time() if now is None else now)
        if self._active_descriptor is not None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Only one Adapter may use the Browser Profile")
        descriptor = self._open_lock()
        acquired = False
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise X2NRuntimeError(
                    ErrorCode.POLICY_BLOCKED,
                    "Only one Adapter may use the Browser Profile",
                ) from error
            acquired = True
            self._active_descriptor = descriptor
            state = self._load_state()
            row = state.setdefault(platform, {})
            self._enforce_interval(
                previous=row.get("last_batch_start"),
                current=current,
                interval=self.batch_interval_seconds,
            )
            row["last_batch_start"] = current
            self._write_state(state)
            yield AdapterLease(platform, self)
        finally:
            self._active_descriptor = None
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _permit_item(self, platform: str, now: float) -> dict[str, object]:
        if self._active_descriptor is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Adapter item access requires the active mutex")
        current = _validate_time(now)
        state = self._load_state()
        row = state.setdefault(_validate_platform(platform), {})
        self._enforce_interval(
            previous=row.get("last_item_observation"),
            current=current,
            interval=self.item_interval_seconds,
        )
        row["last_item_observation"] = current
        self._write_state(state)
        return {
            "automatic_scroll": False,
            "item_observation_permitted": True,
            "platform": platform,
            "policy_id": POLICY_ID,
            "private_path_emitted": False,
        }


@dataclass(frozen=True)
class BatchDeletionDecision:
    outcome: BatchOutcome
    missing_count: int
    tombstone_candidate_count: int
    removed_count: Literal[0] = 0
    content_delete_count: Literal[0] = 0
    physical_delete_count: Literal[0] = 0

    def safe_dict(self) -> dict[str, object]:
        return {
            "content_delete_count": self.content_delete_count,
            "missing_count": self.missing_count,
            "outcome": self.outcome,
            "physical_delete_count": self.physical_delete_count,
            "relation_keys_emitted": False,
            "removed_count": self.removed_count,
            "tombstone_candidate_count": self.tombstone_candidate_count,
        }


class BatchDeletionGuard:
    """Require two consecutive complete successes before candidate status only."""

    def __init__(self) -> None:
        self._complete_missing_counts: dict[str, int] = {}

    def observe(self, outcome: BatchOutcome, missing_relation_keys: Sequence[str]) -> BatchDeletionDecision:
        if outcome not in NON_AUTHORITATIVE_OUTCOMES | {"complete_success"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Batch outcome is unsupported")
        if isinstance(missing_relation_keys, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Missing relations must be a sequence")
        keys = tuple(missing_relation_keys)
        if len(set(keys)) != len(keys) or any(not isinstance(key, str) or not key for key in keys):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Missing relation identities are invalid")
        if outcome in NON_AUTHORITATIVE_OUTCOMES:
            self._complete_missing_counts.clear()
            return BatchDeletionDecision(outcome, len(keys), 0)

        missing = set(keys)
        for key in tuple(self._complete_missing_counts):
            if key not in missing:
                del self._complete_missing_counts[key]
        candidates = 0
        for key in keys:
            count = self._complete_missing_counts.get(key, 0) + 1
            self._complete_missing_counts[key] = count
            if count >= 2:
                candidates += 1
        return BatchDeletionDecision(outcome, len(keys), candidates)
