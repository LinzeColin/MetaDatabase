"""Read-only, digest-only three-role Recovery Key drill mechanism for Stage 7.

The module has no environment discovery, network client or production entry point.  A protected
GitHub-hosted workflow must inject a nonce-bound random sample source and an owner-Recovery-Key
identity materialized under ``/dev/shm``.  Plaintext is streamed only into a bounded SHA-256 sink;
the public result contains aggregate counters and an opaque selection root, never paths, private
digests, ciphertext, plaintext or identity material.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from .adapters import is_age_envelope
from .age_stream import OfficialAgeStream
from .kill_switch import KillId, KillSwitch
from .release_control import GateStatus, ObservationProvenance
from .stage7_ops import (
    RecoveryArtifactRole,
    RecoveryDrillGate,
    RecoveryDrillObservation,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CONTAINER_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^recovery-[0-9a-f]{32}$")
_ROLE_ORDER = tuple(RecoveryArtifactRole)
_OWNER_RECOVERY_KEY_FILENAME = "MooMooAU-Recovery-Key.agekey"
_MAX_STREAM_BYTES = 2_147_483_647
_PREFIX_BYTES = 4096


class RecoveryDrillError(RuntimeError):
    """The drill could not produce a safe aggregate result."""


class RecoveryIdentityOrigin(StrEnum):
    LOCAL_SYNTHETIC = "LOCAL_SYNTHETIC"
    OWNER_RECOVERY_KEY_FILE = "OWNER_RECOVERY_KEY_FILE"


class RecoveryDigestSource(StrEnum):
    RAW_MANIFEST = "RAW_MANIFEST"
    PROCESSED_MANIFEST = "PROCESSED_MANIFEST"
    TIMELINE_PRIVATE_STATE = "TIMELINE_PRIVATE_STATE"


_ROLE_DIGEST_SOURCE = {
    RecoveryArtifactRole.RAW: RecoveryDigestSource.RAW_MANIFEST,
    RecoveryArtifactRole.PROCESSED: RecoveryDigestSource.PROCESSED_MANIFEST,
    RecoveryArtifactRole.TIMELINE: RecoveryDigestSource.TIMELINE_PRIVATE_STATE,
}


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryDrillRunContract:
    """Exact authority envelope; fields are evidence inputs, not platform attestation."""

    run_id: str
    code_commit: str
    container_digest: str
    provenance: ObservationProvenance
    identity_origin: RecoveryIdentityOrigin
    predecessor_ready: bool
    predecessor_task_id: str = "T0706"
    maximum_samples_per_role: int = 1
    maximum_total_samples: int = 3
    private_repository_reads_allowed: bool = False
    private_repository_writes_allowed: bool = False
    gmail_access_allowed: bool = False
    workflow_dispatches_allowed: bool = False
    m3_mutations_allowed: bool = False
    identity_output_allowed: bool = False
    persistent_plaintext_allowed: bool = False

    def __post_init__(self) -> None:
        booleans = (
            self.predecessor_ready,
            self.private_repository_reads_allowed,
            self.private_repository_writes_allowed,
            self.gmail_access_allowed,
            self.workflow_dispatches_allowed,
            self.m3_mutations_allowed,
            self.identity_output_allowed,
            self.persistent_plaintext_allowed,
        )
        expected_origin = (
            RecoveryIdentityOrigin.LOCAL_SYNTHETIC
            if self.provenance is ObservationProvenance.LOCAL_SYNTHETIC
            else RecoveryIdentityOrigin.OWNER_RECOVERY_KEY_FILE
        )
        expected_private_reads = self.provenance is ObservationProvenance.PROTECTED_GITHUB_ACTIONS
        if (
            _RUN_ID.fullmatch(self.run_id) is None
            or _COMMIT.fullmatch(self.code_commit) is None
            or _CONTAINER_DIGEST.fullmatch(self.container_digest) is None
            or not isinstance(self.provenance, ObservationProvenance)
            or not isinstance(self.identity_origin, RecoveryIdentityOrigin)
            or self.identity_origin is not expected_origin
            or self.predecessor_task_id != "T0706"
            or type(self.maximum_samples_per_role) is not int
            or self.maximum_samples_per_role != 1
            or type(self.maximum_total_samples) is not int
            or self.maximum_total_samples != len(_ROLE_ORDER)
            or not all(type(value) is bool for value in booleans)
            or self.private_repository_reads_allowed is not expected_private_reads
            or any(booleans[2:])
        ):
            raise RecoveryDrillError("recovery drill contract exceeds the frozen boundary")

    def __repr__(self) -> str:
        return (
            "RecoveryDrillRunContract(run_id=<opaque>, code_commit=<public>, "
            f"provenance={self.provenance.value!r}, "
            f"identity_origin={self.identity_origin.value!r}, "
            f"predecessor_ready={self.predecessor_ready})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecoverySampleDescriptor:
    """Private manifest/state binding for one nonce-selected ciphertext stream."""

    role: RecoveryArtifactRole
    digest_source: RecoveryDigestSource
    expected_ciphertext_sha256: str
    expected_plaintext_sha256: str
    selection_nonce_sha256: str
    opaque_sample_id: str

    def __post_init__(self) -> None:
        digests = (
            self.expected_ciphertext_sha256,
            self.expected_plaintext_sha256,
            self.selection_nonce_sha256,
            self.opaque_sample_id,
        )
        if (
            not isinstance(self.role, RecoveryArtifactRole)
            or not isinstance(self.digest_source, RecoveryDigestSource)
            or self.digest_source is not _ROLE_DIGEST_SOURCE.get(self.role)
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in digests
            )
        ):
            raise RecoveryDrillError("recovery sample descriptor is invalid")

    def __repr__(self) -> str:
        return (
            f"RecoverySampleDescriptor(role={self.role.value!r}, "
            f"digest_source={self.digest_source.value!r}, private_values=<redacted>)"
        )


@dataclass(slots=True, repr=False)
class RecoverySampleStream:
    descriptor: RecoverySampleDescriptor
    ciphertext: BinaryIO

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, RecoverySampleDescriptor) or not callable(
            getattr(self.ciphertext, "read", None)
        ):
            raise RecoveryDrillError("recovery sample stream is invalid")

    def __repr__(self) -> str:
        return f"RecoverySampleStream(role={self.descriptor.role.value!r}, stream=<redacted>)"


class RandomRecoverySampleSource(Protocol):
    """Open exactly one nonce-bound random sample for the requested private role."""

    def open_random(
        self,
        role: RecoveryArtifactRole,
        selection_nonce: bytes,
    ) -> AbstractContextManager[RecoverySampleStream]: ...


class _BinaryReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class _BinaryWriter(Protocol):
    def write(self, value: bytes) -> int: ...


class RecoveryStreamDecryptor(Protocol):
    def decrypt_stream(self, source: _BinaryReader, sink: _BinaryWriter) -> None: ...


@dataclass(frozen=True, slots=True)
class RecoveryDrillSafetySnapshot:
    identity_disclosures: int
    persistent_plaintext_objects: int
    private_values_recorded: int

    def __post_init__(self) -> None:
        counters = (
            self.identity_disclosures,
            self.persistent_plaintext_objects,
            self.private_values_recorded,
        )
        if any(type(value) is not int or value < 0 for value in counters):
            raise RecoveryDrillError("recovery safety counters are invalid")


class RecoveryDrillSafetyAudit(Protocol):
    """Return cumulative protected log/artifact findings before and after the drill."""

    def snapshot(self) -> RecoveryDrillSafetySnapshot: ...


class OfficialRecoveryStreamDecryptor:
    """Use official age with an identity path; never return recovered plaintext bytes."""

    def __init__(
        self,
        age: OfficialAgeStream,
        identity_path: Path,
        *,
        allowed_tmpfs_roots: tuple[Path, ...] = (Path("/dev/shm"),),
    ) -> None:
        if (
            not isinstance(age, OfficialAgeStream)
            or not isinstance(identity_path, Path)
            or type(allowed_tmpfs_roots) is not tuple
            or not allowed_tmpfs_roots
            or any(not isinstance(root, Path) for root in allowed_tmpfs_roots)
            or len(set(allowed_tmpfs_roots)) != len(allowed_tmpfs_roots)
        ):
            raise RecoveryDrillError("recovery age decryptor contract is invalid")
        self._age = age
        self._identity_path = identity_path
        self._allowed_tmpfs_roots = allowed_tmpfs_roots

    @property
    def protected_identity_contract(self) -> bool:
        if (
            self._allowed_tmpfs_roots != (Path("/dev/shm"),)
            or self._identity_path.name != _OWNER_RECOVERY_KEY_FILENAME
            or self._identity_path.is_symlink()
        ):
            return False
        try:
            root = Path("/dev/shm").resolve(strict=True)
            identity = self._identity_path.resolve(strict=True)
            mode = identity.stat().st_mode
        except (OSError, RuntimeError):
            return False
        return identity.is_file() and mode & 0o077 == 0 and identity.is_relative_to(root)

    def decrypt_stream(self, source: _BinaryReader, sink: _BinaryWriter) -> None:
        self._age.decrypt_stream(
            self._identity_path,
            cast(BinaryIO, source),
            cast(BinaryIO, sink),
            allowed_tmpfs_roots=self._allowed_tmpfs_roots,
        )

    def __repr__(self) -> str:
        return "OfficialRecoveryStreamDecryptor(identity=<redacted>, roots=<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryDrillRunResult:
    contract: RecoveryDrillRunContract
    observation: RecoveryDrillObservation
    gate_status: GateStatus
    reason_codes: tuple[str, ...]
    sample_attempt_count: int
    opaque_selection_root: str
    kill_005_triggered: bool
    kill_005_active: bool
    started_at_utc: datetime
    completed_at_utc: datetime

    def __post_init__(self) -> None:
        report = RecoveryDrillGate().evaluate(self.observation)
        role_success = (
            self.observation.attempted_roles == _ROLE_ORDER
            and self.observation.recovered_roles == _ROLE_ORDER
            and self.observation.digest_mismatches == 0
            and self.observation.identity_disclosures == 0
            and self.observation.persistent_plaintext_objects == 0
            and self.observation.private_values_recorded == 0
        )
        if (
            not isinstance(self.contract, RecoveryDrillRunContract)
            or not isinstance(self.observation, RecoveryDrillObservation)
            or self.observation.provenance is not self.contract.provenance
            or self.gate_status is not report.status
            or self.reason_codes != report.reason_codes
            or type(self.sample_attempt_count) is not int
            or self.sample_attempt_count != len(self.observation.attempted_roles)
            or not 0 <= self.sample_attempt_count <= len(_ROLE_ORDER)
            or _SHA256.fullmatch(self.opaque_selection_root) is None
            or type(self.kill_005_triggered) is not bool
            or type(self.kill_005_active) is not bool
            or (not role_success and not self.kill_005_triggered)
            or (role_success and self.kill_005_triggered)
            or (self.kill_005_triggered and not self.kill_005_active)
            or not _is_utc(self.started_at_utc)
            or not _is_utc(self.completed_at_utc)
            or self.completed_at_utc < self.started_at_utc
        ):
            raise RecoveryDrillError("recovery drill result is inconsistent")

    def __repr__(self) -> str:
        return (
            "RecoveryDrillRunResult(private_values=<redacted>, "
            f"gate_status={self.gate_status.value!r}, "
            f"attempted={len(self.observation.attempted_roles)}, "
            f"recovered={len(self.observation.recovered_roles)}, "
            f"kill_005_active={self.kill_005_active})"
        )

    def to_public_dict(self) -> dict[str, object]:
        duration = int((self.completed_at_utc - self.started_at_utc).total_seconds())
        return {
            "schema_version": "moomooau.recovery-drill-public.v1",
            "run_id": self.contract.run_id,
            "code_commit": self.contract.code_commit,
            "container_digest": self.contract.container_digest,
            "provenance": self.contract.provenance.value,
            "identity_origin": self.contract.identity_origin.value,
            "started_at_utc": _utc_text(self.started_at_utc),
            "completed_at_utc": _utc_text(self.completed_at_utc),
            "duration_seconds": duration,
            "required_roles": len(_ROLE_ORDER),
            "roles_attempted": len(self.observation.attempted_roles),
            "roles_recovered": len(self.observation.recovered_roles),
            "digest_mismatches": self.observation.digest_mismatches,
            "identity_disclosures": self.observation.identity_disclosures,
            "persistent_plaintext_objects": self.observation.persistent_plaintext_objects,
            "private_values_recorded": self.observation.private_values_recorded,
            "sample_attempt_count": self.sample_attempt_count,
            "opaque_selection_root": self.opaque_selection_root,
            "gate_status": self.gate_status.value,
            "reason_codes": list(self.reason_codes),
            "kill_005_triggered": self.kill_005_triggered,
            "kill_005_active": self.kill_005_active,
            "m3_budget_override": 0 if self.kill_005_active else None,
            "m3_mutations_during_drill": 0,
            "gmail_calls": 0,
            "private_repository_writes": 0,
            "workflow_dispatches": 0,
            "final_stage7_claimed": False,
        }


class RecoveryDrillRunner:
    """Recover Raw, Processed and Timeline in order; fail fast and arm KILL-005."""

    def __init__(
        self,
        source: RandomRecoverySampleSource,
        decryptor: RecoveryStreamDecryptor,
        safety_audit: RecoveryDrillSafetyAudit,
        kill_switch: KillSwitch,
        *,
        clock: Callable[[], datetime] | None = None,
        nonce_source: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        self._source = source
        self._decryptor = decryptor
        self._safety_audit = safety_audit
        self._kill_switch = kill_switch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._nonce_source = nonce_source

    def run(self, contract: RecoveryDrillRunContract) -> RecoveryDrillRunResult:
        if not isinstance(contract, RecoveryDrillRunContract) or not contract.predecessor_ready:
            raise RecoveryDrillError("T0706 protected predecessor gate is blocked")
        if contract.provenance is ObservationProvenance.PROTECTED_GITHUB_ACTIONS and (
            not isinstance(self._decryptor, OfficialRecoveryStreamDecryptor)
            or not self._decryptor.protected_identity_contract
        ):
            raise RecoveryDrillError("protected drill requires official age and /dev/shm identity")
        active = self._kill_switch.active_impact
        if active is not None and active.kill_id is not KillId.KILL_005:
            raise RecoveryDrillError("a different Kill Criterion blocks the recovery drill")

        try:
            safety_before = self._safety_audit.snapshot()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            raise RecoveryDrillError("recovery safety preflight is unavailable") from None
        if not isinstance(safety_before, RecoveryDrillSafetySnapshot):
            raise RecoveryDrillError("recovery safety preflight is invalid")
        started = _require_utc(self._clock())
        attempted: list[RecoveryArtifactRole] = []
        recovered: list[RecoveryArtifactRole] = []
        selected: list[tuple[RecoveryArtifactRole, str]] = []
        digest_mismatches = 0
        try:
            run_nonce = self._nonce_source(32)
            if type(run_nonce) is not bytes or len(run_nonce) != 32:
                raise RecoveryDrillError("recovery selection nonce is invalid")
            for role in _ROLE_ORDER:
                attempted.append(role)
                role_nonce = hashlib.sha256(
                    b"moomooau-recovery-drill-v1\x00"
                    + run_nonce
                    + b"\x00"
                    + role.value.encode("ascii")
                ).digest()
                try:
                    self._recover_role(role, role_nonce, selected)
                except _RecoveryDigestMismatch:
                    digest_mismatches += 1
                    break
                recovered.append(role)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass

        try:
            safety_after = self._safety_audit.snapshot()
            safety_delta = _safety_delta(safety_before, safety_after)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self._kill_switch.trigger(KillId.KILL_005)
            raise RecoveryDrillError("recovery safety postflight is unavailable") from None
        role_success = (
            tuple(attempted) == _ROLE_ORDER
            and tuple(recovered) == _ROLE_ORDER
            and digest_mismatches == 0
            and safety_delta.identity_disclosures == 0
            and safety_delta.persistent_plaintext_objects == 0
            and safety_delta.private_values_recorded == 0
        )
        kill_triggered = not role_success
        if kill_triggered:
            impact = self._kill_switch.trigger(KillId.KILL_005)
            if impact.m3_enabled or impact.raw_enabled or impact.production_enabled:
                raise RecoveryDrillError("KILL-005 did not close M3 and new writes")
        completed = _require_utc(self._clock())
        observation = RecoveryDrillObservation(
            provenance=contract.provenance,
            observed_at_utc=completed,
            attempted_roles=tuple(attempted),
            recovered_roles=tuple(recovered),
            digest_mismatches=digest_mismatches,
            identity_disclosures=safety_delta.identity_disclosures,
            persistent_plaintext_objects=safety_delta.persistent_plaintext_objects,
            private_values_recorded=safety_delta.private_values_recorded,
        )
        report = RecoveryDrillGate().evaluate(observation)
        return RecoveryDrillRunResult(
            contract=contract,
            observation=observation,
            gate_status=report.status,
            reason_codes=report.reason_codes,
            sample_attempt_count=len(attempted),
            opaque_selection_root=_selection_root(selected),
            kill_005_triggered=kill_triggered,
            kill_005_active=(
                self._kill_switch.active_impact is not None
                and self._kill_switch.active_impact.kill_id is KillId.KILL_005
            ),
            started_at_utc=started,
            completed_at_utc=completed,
        )

    def _recover_role(
        self,
        role: RecoveryArtifactRole,
        nonce: bytes,
        selected: list[tuple[RecoveryArtifactRole, str]],
    ) -> None:
        with self._source.open_random(role, nonce) as sample:
            if not isinstance(sample, RecoverySampleStream):
                raise RecoveryDrillError("random recovery source returned an invalid stream")
            descriptor = sample.descriptor
            if (
                descriptor.role is not role
                or descriptor.selection_nonce_sha256 != hashlib.sha256(nonce).hexdigest()
            ):
                raise RecoveryDrillError("random recovery selection is not nonce bound")
            selected.append((role, descriptor.opaque_sample_id))
            reader = _DigestingReader(sample.ciphertext)
            plaintext_sink = _DigestSink()
            self._decryptor.decrypt_stream(reader, plaintext_sink)
            if (
                not reader.exhausted
                or not is_age_envelope(reader.prefix)
                or reader.hexdigest != descriptor.expected_ciphertext_sha256
                or plaintext_sink.hexdigest != descriptor.expected_plaintext_sha256
            ):
                raise _RecoveryDigestMismatch


class _RecoveryDigestMismatch(RecoveryDrillError):
    pass


class _DigestingReader:
    def __init__(self, source: BinaryIO) -> None:
        self._source = source
        self._digest = hashlib.sha256()
        self._prefix = bytearray()
        self._total = 0
        self.exhausted = False

    def read(self, size: int = -1) -> bytes:
        value = self._source.read(size)
        if not isinstance(value, bytes):
            raise RecoveryDrillError("ciphertext stream returned a non-bytes value")
        if not value:
            self.exhausted = True
            return b""
        self._total += len(value)
        if self._total > _MAX_STREAM_BYTES:
            raise RecoveryDrillError("recovery ciphertext exceeds the bounded stream limit")
        if len(self._prefix) < _PREFIX_BYTES:
            remaining = _PREFIX_BYTES - len(self._prefix)
            self._prefix.extend(value[:remaining])
        self._digest.update(value)
        return value

    @property
    def prefix(self) -> bytes:
        return bytes(self._prefix)

    @property
    def hexdigest(self) -> str:
        return self._digest.hexdigest()


class _DigestSink:
    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._total = 0

    def write(self, value: bytes) -> int:
        if not isinstance(value, bytes):
            raise RecoveryDrillError("recovered plaintext stream returned a non-bytes value")
        chunk = value
        self._total += len(chunk)
        if self._total > _MAX_STREAM_BYTES:
            raise RecoveryDrillError("recovered plaintext exceeds the bounded stream limit")
        self._digest.update(chunk)
        return len(chunk)

    @property
    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def _selection_root(selected: list[tuple[RecoveryArtifactRole, str]]) -> str:
    payload = [
        {"role": role.value, "opaque_sample_id": opaque_sample_id}
        for role, opaque_sample_id in selected
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _safety_delta(
    before: RecoveryDrillSafetySnapshot,
    after: RecoveryDrillSafetySnapshot,
) -> RecoveryDrillSafetySnapshot:
    if not isinstance(after, RecoveryDrillSafetySnapshot):
        raise RecoveryDrillError("recovery safety postflight is invalid")
    values = (
        after.identity_disclosures - before.identity_disclosures,
        after.persistent_plaintext_objects - before.persistent_plaintext_objects,
        after.private_values_recorded - before.private_values_recorded,
    )
    if any(value < 0 for value in values):
        raise RecoveryDrillError("recovery safety counters moved backwards")
    return RecoveryDrillSafetySnapshot(*values)


def _require_utc(value: datetime) -> datetime:
    if not _is_utc(value):
        raise RecoveryDrillError("recovery drill clock is not UTC")
    return value


def _is_utc(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
