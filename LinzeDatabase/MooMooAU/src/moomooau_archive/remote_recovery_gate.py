"""Remote refetch and decrypt gate required before any M3 mutation."""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .adapters import is_age_envelope
from .age_stream import OfficialAgeStream
from .canonical_raw import CanonicalRaw
from .processed_commit import (
    PrivateProcessedObject,
    ProcessedCiphertextStore,
    ProcessedCommitPlan,
    ProcessedObjectRole,
)
from .processed_models import ProcessingState
from .processed_product import ProcessedBundle, ProcessedFormat
from .raw_commit import (
    AppendOnlyCiphertextStore,
    PrivateCiphertextObject,
    RawCommitPlan,
    RawObjectRole,
)
from .sender_registry import MessageVerification, SenderDecision, VerificationPhase

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROOF_SENTINEL = object()
_SAFE_PROCESSED_STATES = {
    ProcessingState.COMPLETE,
    ProcessingState.WAITING_FOR_PDF_PASSWORD,
    ProcessingState.UNSUPPORTED,
    ProcessingState.RAW_ONLY,
}


class RecoveryScope(StrEnum):
    RAW_ONLY = "RAW_ONLY"
    RAW_AND_PROCESSED = "RAW_AND_PROCESSED"


class RemoteRecoveryError(RuntimeError):
    """A private object could not be proven recoverable; diagnostics stay redacted."""


class RemoteCiphertextReader(Protocol):
    def fetch(self, relative_path: str) -> bytes | None: ...


class CiphertextDecryptor(Protocol):
    def decrypt(self, ciphertext: bytes) -> bytes: ...


class RepositoryCiphertextReader:
    """Read the Raw and Processed namespaces from the same private repository adapters."""

    _RAW_PREFIXES = (
        "MooMooAU/Raw/",
        "MooMooAU/Manifests/raw/",
    )
    _PROCESSED_PREFIXES = (
        "MooMooAU/Processed/",
        "MooMooAU/Manifests/processed/",
    )
    _CURRENT_PREFIX = "MooMooAU/State/processed-current/"

    def __init__(
        self,
        raw_store: AppendOnlyCiphertextStore,
        processed_store: ProcessedCiphertextStore,
    ) -> None:
        self._raw_store = raw_store
        self._processed_store = processed_store

    def fetch(self, relative_path: str) -> bytes | None:
        if relative_path.startswith(self._RAW_PREFIXES):
            return self._raw_store.fetch(relative_path)
        if relative_path.startswith(self._CURRENT_PREFIX):
            current = self._processed_store.fetch_current(relative_path)
            return bytes(current.ciphertext) if current is not None else None
        if relative_path.startswith(self._PROCESSED_PREFIXES):
            return self._processed_store.fetch_immutable(relative_path)
        raise RemoteRecoveryError("private recovery path is outside the archive namespaces")


class OfficialAgeDecryptor:
    """Decrypt through official age pipes using an identity restricted to approved tmpfs."""

    def __init__(
        self,
        age: OfficialAgeStream,
        identity_path: Path,
        *,
        allowed_tmpfs_roots: tuple[Path, ...] = (Path("/dev/shm"),),
    ) -> None:
        if not allowed_tmpfs_roots:
            raise RemoteRecoveryError("at least one protected tmpfs root is required")
        self._age = age
        self._identity_path = identity_path
        self._allowed_tmpfs_roots = allowed_tmpfs_roots

    def decrypt(self, ciphertext: bytes) -> bytes:
        source = io.BytesIO(ciphertext)
        sink = io.BytesIO()
        self._age.decrypt_stream(
            self._identity_path,
            source,
            sink,
            allowed_tmpfs_roots=self._allowed_tmpfs_roots,
        )
        return sink.getvalue()


@dataclass(frozen=True, slots=True, repr=False)
class MessageRecoveryProof:
    """Unforgeable-in-process capability binding one Gmail message to recovered data."""

    message_id: str
    internal_date_ms: int
    source_id: str
    raw_plaintext_sha256: str
    raw_ciphertext_sha256: str
    verification_digest: str
    recovery_scope: RecoveryScope
    processed_state: ProcessingState
    recovered_object_count: int
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._sentinel is not _PROOF_SENTINEL
            or not self.message_id
            or type(self.internal_date_ms) is not int
            or self.internal_date_ms < 0
            or _SHA256.fullmatch(self.source_id) is None
            or _SHA256.fullmatch(self.raw_plaintext_sha256) is None
            or _SHA256.fullmatch(self.raw_ciphertext_sha256) is None
            or _SHA256.fullmatch(self.verification_digest) is None
            or not isinstance(self.recovery_scope, RecoveryScope)
            or self.processed_state not in _SAFE_PROCESSED_STATES
            or (
                self.recovery_scope is RecoveryScope.RAW_ONLY
                and self.processed_state is not ProcessingState.RAW_ONLY
            )
            or type(self.recovered_object_count) is not int
            or self.recovered_object_count < 2
        ):
            raise RemoteRecoveryError("remote recovery proof is invalid")

    def __repr__(self) -> str:
        return (
            "MessageRecoveryProof(message_id=<redacted>, internal_date_ms=<redacted>, "
            "source_id=<redacted>, raw_plaintext_sha256=<redacted>, "
            "raw_ciphertext_sha256=<redacted>, verification_digest=<redacted>, "
            f"recovery_scope={self.recovery_scope.value!r}, "
            f"processed_state={self.processed_state.value!r}, "
            f"recovered_object_count={self.recovered_object_count})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class _RecoveredObject:
    ciphertext_sha256: str
    plaintext_sha256: str
    plaintext: bytes = field(repr=False)


class RemoteRecoveryGate:
    """Refetch every expected ciphertext and verify its decrypted plaintext digest."""

    def __init__(self, reader: RemoteCiphertextReader, decryptor: CiphertextDecryptor) -> None:
        self._reader = reader
        self._decryptor = decryptor

    def verify(
        self,
        canonical: CanonicalRaw,
        first_verification: MessageVerification,
        raw_plan: RawCommitPlan,
        processed_bundle: ProcessedBundle,
        processed_plan: ProcessedCommitPlan,
    ) -> MessageRecoveryProof:
        verification_digest = first_verification.verification_digest
        if (
            not self._raw_inputs_match(canonical, first_verification, raw_plan)
            or verification_digest is None
            or raw_plan.opaque_message_id != processed_bundle.source_id
            or processed_plan.source_id != processed_bundle.source_id
            or processed_plan.decision.candidate_snapshot_root != processed_bundle.snapshot_root
            or processed_bundle.processing_state not in _SAFE_PROCESSED_STATES
        ):
            raise RemoteRecoveryError("recovery inputs are not bound to one verified message")
        recovered = 0
        raw_ciphertext_sha256: str | None = None
        for raw_item in raw_plan.objects:
            recovered_raw = self._verify_object(raw_item)
            if raw_item.role is RawObjectRole.MESSAGE:
                raw_ciphertext_sha256 = recovered_raw.ciphertext_sha256
            recovered += 1
        if raw_ciphertext_sha256 is None:
            raise RemoteRecoveryError("Raw recovery plan has no message object")
        recovered_processed: dict[str, _RecoveredObject] = {}
        processed_manifest: PrivateProcessedObject | None = None
        for processed_item in processed_plan.immutable_objects:
            if processed_item.role is ProcessedObjectRole.MANIFEST:
                processed_manifest = processed_item
                continue
            recovered_processed[processed_item.relative_path] = self._verify_object(processed_item)
            recovered += 1
        if processed_manifest is None:
            raise RemoteRecoveryError("Processed recovery plan has no manifest")
        recovered_manifest = self._recover(processed_manifest)
        self._validate_processed_manifest(
            recovered_manifest.plaintext,
            processed_bundle,
            processed_plan,
            recovered_processed,
        )
        recovered += 1
        if processed_plan.current_pointer is not None:
            self._verify_object(processed_plan.current_pointer)
            recovered += 1

        return MessageRecoveryProof(
            message_id=canonical.message_id,
            internal_date_ms=canonical.internal_date_ms,
            source_id=raw_plan.opaque_message_id,
            raw_plaintext_sha256=canonical.plaintext_sha256,
            raw_ciphertext_sha256=raw_ciphertext_sha256,
            verification_digest=verification_digest,
            recovery_scope=RecoveryScope.RAW_AND_PROCESSED,
            processed_state=processed_bundle.processing_state,
            recovered_object_count=recovered,
            _sentinel=_PROOF_SENTINEL,
        )

    def verify_raw_only(
        self,
        canonical: CanonicalRaw,
        first_verification: MessageVerification,
        raw_plan: RawCommitPlan,
    ) -> MessageRecoveryProof:
        """Recover every Raw object without creating a Processed product or M3 side effect."""

        verification_digest = first_verification.verification_digest
        if (
            not self._raw_inputs_match(canonical, first_verification, raw_plan)
            or verification_digest is None
        ):
            raise RemoteRecoveryError("Raw-only recovery inputs are not bound")
        recovered = 0
        raw_ciphertext_sha256: str | None = None
        for item in raw_plan.objects:
            recovered_raw = self._verify_object(item)
            if item.role is RawObjectRole.MESSAGE:
                raw_ciphertext_sha256 = recovered_raw.ciphertext_sha256
            recovered += 1
        if raw_ciphertext_sha256 is None:
            raise RemoteRecoveryError("Raw-only recovery plan has no message object")
        return MessageRecoveryProof(
            message_id=canonical.message_id,
            internal_date_ms=canonical.internal_date_ms,
            source_id=raw_plan.opaque_message_id,
            raw_plaintext_sha256=canonical.plaintext_sha256,
            raw_ciphertext_sha256=raw_ciphertext_sha256,
            verification_digest=verification_digest,
            recovery_scope=RecoveryScope.RAW_ONLY,
            processed_state=ProcessingState.RAW_ONLY,
            recovered_object_count=recovered,
            _sentinel=_PROOF_SENTINEL,
        )

    @staticmethod
    def _raw_inputs_match(
        canonical: CanonicalRaw,
        first_verification: MessageVerification,
        raw_plan: RawCommitPlan,
    ) -> bool:
        raw_messages = [item for item in raw_plan.objects if item.role is RawObjectRole.MESSAGE]
        return (
            first_verification.phase is VerificationPhase.PRE_RAW
            and first_verification.decision is SenderDecision.VERIFIED
            and first_verification.raw_fetch_permit is not None
            and first_verification.verification_digest is not None
            and first_verification.message_id == canonical.message_id
            and first_verification.internal_date_ms == canonical.internal_date_ms
            and len(raw_messages) == 1
            and raw_messages[0].plaintext_sha256 == canonical.plaintext_sha256
        )

    def _recover(
        self,
        item: PrivateCiphertextObject | PrivateProcessedObject,
    ) -> _RecoveredObject:
        remote = self._reader.fetch(item.relative_path)
        if remote is None or not is_age_envelope(remote):
            raise RemoteRecoveryError("remote ciphertext is missing or differs from the commit")
        try:
            plaintext = self._decryptor.decrypt(remote)
        except Exception as exc:
            raise RemoteRecoveryError("remote ciphertext decryption failed") from exc
        return _RecoveredObject(
            ciphertext_sha256=hashlib.sha256(remote).hexdigest(),
            plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
            plaintext=plaintext,
        )

    def _verify_object(
        self,
        item: PrivateCiphertextObject | PrivateProcessedObject,
    ) -> _RecoveredObject:
        recovered = self._recover(item)
        if recovered.plaintext_sha256 != item.plaintext_sha256:
            raise RemoteRecoveryError("remote plaintext digest does not match the commit")
        return recovered

    @staticmethod
    def _validate_processed_manifest(
        payload: bytes,
        bundle: ProcessedBundle,
        plan: ProcessedCommitPlan,
        recovered: dict[str, _RecoveredObject],
    ) -> None:
        if len(payload) > 4 * 1024 * 1024:
            raise RemoteRecoveryError("remote Processed manifest exceeds the safe limit")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RemoteRecoveryError("remote Processed manifest is invalid") from exc
        required = {
            "schema_version",
            "source_id",
            "parser_name",
            "parser_version",
            "output_schema_version",
            "processing_state",
            "business_root",
            "snapshot_root",
            "key_epoch",
            "artifacts",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RemoteRecoveryError("remote Processed manifest schema is invalid")
        expected_header = {
            "schema_version": "moomooau.private-processed-manifest.v1",
            "source_id": bundle.source_id,
            "parser_name": bundle.parser_name,
            "parser_version": bundle.parser_version,
            "output_schema_version": bundle.schema_version,
            "processing_state": bundle.processing_state.value,
            "business_root": bundle.business_root,
            "snapshot_root": bundle.snapshot_root,
            "key_epoch": plan.key_epoch,
        }
        if any(value.get(key) != expected for key, expected in expected_header.items()):
            raise RemoteRecoveryError("remote Processed manifest identity differs")
        data_objects = [
            item for item in plan.immutable_objects if item.role is ProcessedObjectRole.DATASET
        ]
        if len(data_objects) != len(bundle.artifacts):
            raise RemoteRecoveryError("Processed artifacts and plan differ")
        expected_artifacts: list[dict[str, str]] = []
        for artifact, item in zip(bundle.artifacts, data_objects, strict=True):
            recovered_item = recovered.get(item.relative_path)
            if recovered_item is None:
                raise RemoteRecoveryError("remote Processed dataset is missing")
            extension = "jsonl" if artifact.format is ProcessedFormat.JSONL else "parquet"
            if not item.relative_path.endswith("." + extension + ".age"):
                raise RemoteRecoveryError("remote Processed dataset path is invalid")
            expected_artifacts.append(
                {
                    "dataset_name": artifact.dataset_name,
                    "format": artifact.format.value,
                    "relative_path": item.relative_path,
                    "plaintext_sha256": artifact.plaintext_sha256,
                    "ciphertext_sha256": recovered_item.ciphertext_sha256,
                    "schema_version": artifact.schema_version,
                }
            )
        if value.get("artifacts") != expected_artifacts:
            raise RemoteRecoveryError("remote Processed manifest artifacts differ")


class MemoryRemoteCiphertextReader:
    """Synthetic remote used to prove the gate without network or persistent data."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.fetch_calls = 0

    def put(self, relative_path: str, ciphertext: bytes) -> None:
        if not is_age_envelope(ciphertext):
            raise RemoteRecoveryError("synthetic remote accepts age ciphertext only")
        self._objects[relative_path] = bytes(ciphertext)

    def fetch(self, relative_path: str) -> bytes | None:
        self.fetch_calls += 1
        value = self._objects.get(relative_path)
        return bytes(value) if value is not None else None

    def replace_for_test(self, relative_path: str, ciphertext: bytes) -> None:
        """Fault injection only; invalid bytes are intentionally permitted here."""

        if relative_path not in self._objects:
            raise KeyError(relative_path)
        self._objects[relative_path] = bytes(ciphertext)
