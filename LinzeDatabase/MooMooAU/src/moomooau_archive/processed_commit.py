"""Age-only versioned Processed commits, blue-green comparison and strict current CAS."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast

from .age_stream import OfficialAgeStream, is_age_envelope
from .github_guard import (
    CONTENT_APPEND_MESSAGE,
    CONTENT_POINTER_MESSAGE,
    GITHUB_API_VERSION,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    InstallationToken,
    RepositoryLocator,
    content_url,
)
from .http_boundary import HttpRequest
from .processed_product import ProcessedBundle, ProcessedFormat
from .secret_values import SecretBytes

_OPAQUE_ID = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_PARSER_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PRIVATE_PATH = re.compile(r"^MooMooAU/[A-Za-z0-9._/-]+\.age$")
_CURRENT_PATH = re.compile(r"^MooMooAU/State/processed-current/[0-9a-f]{64}\.json\.age$")
_MANIFEST_PATH = re.compile(
    r"^MooMooAU/Manifests/processed/[a-z][a-z0-9_-]{2,63}/"
    r"[1-9][0-9]*\.[0-9]+\.[0-9]+/[0-9a-f]{64}\.json\.age$"
)
_APPROVAL_SENTINEL = object()
_POINTER_SENTINEL = object()


class ProcessedCommitError(RuntimeError):
    """Processed planning or persistence failed with redacted diagnostics."""


class ProcessedObjectRole(StrEnum):
    DATASET = "DATASET"
    MANIFEST = "MANIFEST"
    CURRENT_POINTER = "CURRENT_POINTER"


class PromotionAction(StrEnum):
    INITIAL_PROMOTION = "INITIAL_PROMOTION"
    IDEMPOTENT_CURRENT = "IDEMPOTENT_CURRENT"
    OBSERVATION_WINDOW_PENDING = "OBSERVATION_WINDOW_PENDING"
    SEMANTICALLY_EQUAL_PROMOTION = "SEMANTICALLY_EQUAL_PROMOTION"
    PROTECTED_APPROVAL_REQUIRED = "PROTECTED_APPROVAL_REQUIRED"
    PROTECTED_APPROVED_PROMOTION = "PROTECTED_APPROVED_PROMOTION"
    VERSION_ROLLBACK_BLOCKED = "VERSION_ROLLBACK_BLOCKED"
    VERSION_REUSE_CONFLICT = "VERSION_REUSE_CONFLICT"


class ProcessedCommitState(StrEnum):
    PRIVATE_PROCESSED_COMMITTED_RECOVERY_PENDING = "PRIVATE_PROCESSED_COMMITTED_RECOVERY_PENDING"
    CANDIDATE_COMMITTED_CURRENT_UNCHANGED = "CANDIDATE_COMMITTED_CURRENT_UNCHANGED"


@dataclass(frozen=True, slots=True, repr=False)
class CurrentProcessedPointer:
    source_id: str
    parser_name: str
    parser_version: str
    schema_version: str
    business_root: str
    snapshot_root: str
    manifest_path: str
    key_epoch: str
    generation: int
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._sentinel is not _POINTER_SENTINEL
            or _OPAQUE_ID.fullmatch(self.source_id) is None
            or _PARSER_NAME.fullmatch(self.parser_name) is None
            or _SEMVER.fullmatch(self.parser_version) is None
            or _SEMVER.fullmatch(self.schema_version) is None
            or _SHA256.fullmatch(self.business_root) is None
            or _SHA256.fullmatch(self.snapshot_root) is None
            or _MANIFEST_PATH.fullmatch(self.manifest_path) is None
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or type(self.generation) is not int
            or self.generation <= 0
        ):
            raise ProcessedCommitError("processed current pointer is invalid")

    def __repr__(self) -> str:
        return (
            "CurrentProcessedPointer(source_id=<redacted>, "
            f"parser_name={self.parser_name!r}, parser_version={self.parser_version!r}, "
            f"schema_version={self.schema_version!r}, business_root=<redacted>, "
            "snapshot_root=<redacted>, manifest_path=<redacted>, key_epoch=<redacted>, "
            f"generation={self.generation})"
        )

    def to_bytes(self) -> bytes:
        return _canonical_json(
            {
                "schema_version": "moomooau.processed-current.v1",
                "source_id": self.source_id,
                "parser_name": self.parser_name,
                "parser_version": self.parser_version,
                "output_schema_version": self.schema_version,
                "business_root": self.business_root,
                "snapshot_root": self.snapshot_root,
                "manifest_path": self.manifest_path,
                "key_epoch": self.key_epoch,
                "generation": self.generation,
            }
        )

    @classmethod
    def from_bytes(cls, payload: bytes) -> CurrentProcessedPointer:
        if len(payload) > 1024 * 1024:
            raise ProcessedCommitError("processed current pointer exceeds the safe limit")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProcessedCommitError("processed current pointer is not valid JSON") from exc
        required = {
            "schema_version",
            "source_id",
            "parser_name",
            "parser_version",
            "output_schema_version",
            "business_root",
            "snapshot_root",
            "manifest_path",
            "key_epoch",
            "generation",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("schema_version") != "moomooau.processed-current.v1"
        ):
            raise ProcessedCommitError("processed current pointer schema is invalid")
        return cls(
            source_id=_required_string(value, "source_id"),
            parser_name=_required_string(value, "parser_name"),
            parser_version=_required_string(value, "parser_version"),
            schema_version=_required_string(value, "output_schema_version"),
            business_root=_required_string(value, "business_root"),
            snapshot_root=_required_string(value, "snapshot_root"),
            manifest_path=_required_string(value, "manifest_path"),
            key_epoch=_required_string(value, "key_epoch"),
            generation=_required_integer(value, "generation"),
            _sentinel=_POINTER_SENTINEL,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProtectedPromotionApproval:
    source_id: str
    incumbent_snapshot_root: str
    candidate_snapshot_root: str
    issued_at_utc: datetime
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        offset = self.issued_at_utc.utcoffset()
        if (
            self._sentinel is not _APPROVAL_SENTINEL
            or _OPAQUE_ID.fullmatch(self.source_id) is None
            or _SHA256.fullmatch(self.incumbent_snapshot_root) is None
            or _SHA256.fullmatch(self.candidate_snapshot_root) is None
            or self.issued_at_utc.tzinfo is None
            or offset is None
            or offset.total_seconds() != 0
        ):
            raise ProcessedCommitError("protected promotion approval is invalid")

    def __repr__(self) -> str:
        return (
            "ProtectedPromotionApproval(source_id=<redacted>, "
            "incumbent_snapshot_root=<redacted>, candidate_snapshot_root=<redacted>, "
            "issued_at_utc=<redacted>)"
        )

    @classmethod
    def verify_signed_payload(
        cls,
        payload: bytes,
        signature_hex: str,
        verification_key: SecretBytes,
    ) -> ProtectedPromotionApproval:
        key = verification_key.reveal()
        if len(key) < 32 or re.fullmatch(r"[0-9a-f]{64}", signature_hex) is None:
            raise ProcessedCommitError("protected approval verification input is invalid")
        expected = hmac.digest(key, payload, "sha256").hex()
        if not hmac.compare_digest(signature_hex, expected):
            raise ProcessedCommitError("protected promotion approval signature is invalid")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProcessedCommitError("protected approval payload is invalid") from exc
        required = {
            "schema_version",
            "decision",
            "source_id",
            "incumbent_snapshot_root",
            "candidate_snapshot_root",
            "issued_at_utc",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("schema_version") != "moomooau.parser-promotion-approval.v1"
            or value.get("decision") != "APPROVE"
        ):
            raise ProcessedCommitError("protected approval payload schema is invalid")
        return cls(
            source_id=_required_string(value, "source_id"),
            incumbent_snapshot_root=_required_string(value, "incumbent_snapshot_root"),
            candidate_snapshot_root=_required_string(value, "candidate_snapshot_root"),
            issued_at_utc=_parse_utc(_required_string(value, "issued_at_utc")),
            _sentinel=_APPROVAL_SENTINEL,
        )


@dataclass(frozen=True, slots=True)
class BlueGreenDecision:
    action: PromotionAction
    promote_current: bool
    candidate_snapshot_root: str
    incumbent_snapshot_root: str | None
    reason_code: str

    def __post_init__(self) -> None:
        promotable = {
            PromotionAction.INITIAL_PROMOTION,
            PromotionAction.SEMANTICALLY_EQUAL_PROMOTION,
            PromotionAction.PROTECTED_APPROVED_PROMOTION,
        }
        if (
            _SHA256.fullmatch(self.candidate_snapshot_root) is None
            or (
                self.incumbent_snapshot_root is not None
                and _SHA256.fullmatch(self.incumbent_snapshot_root) is None
            )
            or not self.reason_code
            or self.promote_current != (self.action in promotable)
        ):
            raise ProcessedCommitError("blue-green decision is invalid")


class ParserBlueGreenComparator:
    minimum_observation_days = 14

    def compare(
        self,
        candidate: ProcessedBundle,
        incumbent: CurrentProcessedPointer | None,
        *,
        observed_days: int,
        approval: ProtectedPromotionApproval | None = None,
    ) -> BlueGreenDecision:
        if type(observed_days) is not int or observed_days < 0:
            raise ProcessedCommitError("blue-green observation window is invalid")
        if incumbent is None:
            return self._decision(
                PromotionAction.INITIAL_PROMOTION,
                candidate,
                None,
                "NO_INCUMBENT_CURRENT",
            )
        if candidate.source_id != incumbent.source_id:
            raise ProcessedCommitError("blue-green sources do not match")
        candidate_version = _semver_key(candidate.parser_version)
        incumbent_version = _semver_key(incumbent.parser_version)
        if candidate_version < incumbent_version:
            return self._decision(
                PromotionAction.VERSION_ROLLBACK_BLOCKED,
                candidate,
                incumbent,
                "PARSER_VERSION_ROLLBACK_BLOCKED",
            )
        if candidate_version == incumbent_version:
            action = (
                PromotionAction.IDEMPOTENT_CURRENT
                if candidate.snapshot_root == incumbent.snapshot_root
                else PromotionAction.VERSION_REUSE_CONFLICT
            )
            reason = (
                "CANDIDATE_ALREADY_CURRENT"
                if action is PromotionAction.IDEMPOTENT_CURRENT
                else "PARSER_VERSION_REUSED_WITH_DIFFERENT_OUTPUT"
            )
            return self._decision(action, candidate, incumbent, reason)
        if observed_days < self.minimum_observation_days:
            return self._decision(
                PromotionAction.OBSERVATION_WINDOW_PENDING,
                candidate,
                incumbent,
                "FOURTEEN_DAY_OBSERVATION_INCOMPLETE",
            )
        if candidate.business_root == incumbent.business_root:
            return self._decision(
                PromotionAction.SEMANTICALLY_EQUAL_PROMOTION,
                candidate,
                incumbent,
                "BUSINESS_OUTPUT_EQUIVALENT",
            )
        if approval is None:
            return self._decision(
                PromotionAction.PROTECTED_APPROVAL_REQUIRED,
                candidate,
                incumbent,
                "BUSINESS_OUTPUT_CHANGED",
            )
        if (
            approval.source_id != candidate.source_id
            or approval.incumbent_snapshot_root != incumbent.snapshot_root
            or approval.candidate_snapshot_root != candidate.snapshot_root
        ):
            raise ProcessedCommitError("protected approval does not bind the comparison")
        return self._decision(
            PromotionAction.PROTECTED_APPROVED_PROMOTION,
            candidate,
            incumbent,
            "PROTECTED_CHANGE_APPROVAL_VERIFIED",
        )

    @staticmethod
    def _decision(
        action: PromotionAction,
        candidate: ProcessedBundle,
        incumbent: CurrentProcessedPointer | None,
        reason_code: str,
    ) -> BlueGreenDecision:
        return BlueGreenDecision(
            action=action,
            promote_current=action
            in {
                PromotionAction.INITIAL_PROMOTION,
                PromotionAction.SEMANTICALLY_EQUAL_PROMOTION,
                PromotionAction.PROTECTED_APPROVED_PROMOTION,
            },
            candidate_snapshot_root=candidate.snapshot_root,
            incumbent_snapshot_root=(incumbent.snapshot_root if incumbent is not None else None),
            reason_code=reason_code,
        )


@dataclass(frozen=True, slots=True, repr=False)
class PrivateProcessedObject:
    relative_path: str
    role: ProcessedObjectRole
    plaintext_sha256: str
    ciphertext_sha256: str
    ciphertext: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            _PRIVATE_PATH.fullmatch(self.relative_path) is None
            or _SHA256.fullmatch(self.plaintext_sha256) is None
            or _SHA256.fullmatch(self.ciphertext_sha256) is None
            or hashlib.sha256(self.ciphertext).hexdigest() != self.ciphertext_sha256
            or not is_age_envelope(self.ciphertext)
            or (
                self.role is ProcessedObjectRole.CURRENT_POINTER
                and _CURRENT_PATH.fullmatch(self.relative_path) is None
            )
            or (
                self.role is not ProcessedObjectRole.CURRENT_POINTER
                and _CURRENT_PATH.fullmatch(self.relative_path) is not None
            )
        ):
            raise ProcessedCommitError("private Processed ciphertext object is invalid")

    def __repr__(self) -> str:
        return (
            "PrivateProcessedObject(relative_path=<redacted>, "
            f"role={self.role.value!r}, plaintext_sha256=<redacted>, "
            "ciphertext_sha256=<redacted>, ciphertext=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProcessedCommitPlan:
    source_id: str
    parser_name: str
    parser_version: str
    key_epoch: str
    decision: BlueGreenDecision
    immutable_objects: tuple[PrivateProcessedObject, ...]
    current_pointer: PrivateProcessedObject | None
    expected_pointer_revision: str | None

    def __post_init__(self) -> None:
        paths = [item.relative_path for item in self.immutable_objects]
        if (
            _OPAQUE_ID.fullmatch(self.source_id) is None
            or _PARSER_NAME.fullmatch(self.parser_name) is None
            or _SEMVER.fullmatch(self.parser_version) is None
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or not self.immutable_objects
            or self.immutable_objects[-1].role is not ProcessedObjectRole.MANIFEST
            or any(
                item.role is ProcessedObjectRole.CURRENT_POINTER for item in self.immutable_objects
            )
            or len(paths) != len(set(paths))
            or self.decision.promote_current != (self.current_pointer is not None)
            or (
                self.expected_pointer_revision is not None
                and _GIT_REVISION.fullmatch(self.expected_pointer_revision) is None
            )
        ):
            raise ProcessedCommitError("Processed commit plan is invalid")

    def __repr__(self) -> str:
        return (
            "ProcessedCommitPlan(source_id=<redacted>, "
            f"parser_name={self.parser_name!r}, parser_version={self.parser_version!r}, "
            "key_epoch=<redacted>, "
            f"decision={self.decision.action.value!r}, "
            f"immutable_count={len(self.immutable_objects)}, "
            f"current_pointer_present={self.current_pointer is not None}, "
            "expected_pointer_revision=<redacted>)"
        )


class ProcessedCommitPlanner:
    def __init__(self, age: OfficialAgeStream, recipient: str) -> None:
        self._age = age
        self._recipient = recipient

    def plan(
        self,
        bundle: ProcessedBundle,
        decision: BlueGreenDecision,
        incumbent: CurrentProcessedPointer | None,
        *,
        key_epoch: str,
        expected_pointer_revision: str | None,
    ) -> ProcessedCommitPlan:
        if decision.action in {
            PromotionAction.VERSION_ROLLBACK_BLOCKED,
            PromotionAction.VERSION_REUSE_CONFLICT,
        }:
            raise ProcessedCommitError("blocked parser version decision cannot be committed")
        if (
            decision.candidate_snapshot_root != bundle.snapshot_root
            or decision.incumbent_snapshot_root
            != (incumbent.snapshot_root if incumbent is not None else None)
            or _KEY_EPOCH.fullmatch(key_epoch) is None
            or (incumbent is None) != (expected_pointer_revision is None)
            or (
                incumbent is not None
                and _GIT_REVISION.fullmatch(cast(str, expected_pointer_revision)) is None
            )
        ):
            raise ProcessedCommitError("Processed plan inputs are not bound")
        base = (
            f"MooMooAU/Processed/{{dataset}}/v{bundle.schema_version.split('.', 1)[0]}/"
            f"{bundle.parser_name}/{bundle.parser_version}/{bundle.source_id}"
        )
        objects: list[PrivateProcessedObject] = []
        manifest_artifacts: list[dict[str, str]] = []
        for artifact in bundle.artifacts:
            extension = "jsonl" if artifact.format is ProcessedFormat.JSONL else "parquet"
            path = base.format(dataset=artifact.dataset_name) + f".{extension}.age"
            encrypted = self._encrypt(path, ProcessedObjectRole.DATASET, artifact.plaintext)
            objects.append(encrypted)
            manifest_artifacts.append(
                {
                    "dataset_name": artifact.dataset_name,
                    "format": artifact.format.value,
                    "relative_path": path,
                    "plaintext_sha256": artifact.plaintext_sha256,
                    "ciphertext_sha256": encrypted.ciphertext_sha256,
                    "schema_version": artifact.schema_version,
                }
            )
        manifest_path = (
            f"MooMooAU/Manifests/processed/{bundle.parser_name}/"
            f"{bundle.parser_version}/{bundle.source_id}.json.age"
        )
        manifest_plaintext = _canonical_json(
            {
                "schema_version": "moomooau.private-processed-manifest.v1",
                "source_id": bundle.source_id,
                "parser_name": bundle.parser_name,
                "parser_version": bundle.parser_version,
                "output_schema_version": bundle.schema_version,
                "processing_state": bundle.processing_state.value,
                "business_root": bundle.business_root,
                "snapshot_root": bundle.snapshot_root,
                "key_epoch": key_epoch,
                "artifacts": manifest_artifacts,
            }
        )
        objects.append(
            self._encrypt(manifest_path, ProcessedObjectRole.MANIFEST, manifest_plaintext)
        )
        pointer_object: PrivateProcessedObject | None = None
        if decision.promote_current:
            pointer = CurrentProcessedPointer(
                source_id=bundle.source_id,
                parser_name=bundle.parser_name,
                parser_version=bundle.parser_version,
                schema_version=bundle.schema_version,
                business_root=bundle.business_root,
                snapshot_root=bundle.snapshot_root,
                manifest_path=manifest_path,
                key_epoch=key_epoch,
                generation=1 if incumbent is None else incumbent.generation + 1,
                _sentinel=_POINTER_SENTINEL,
            )
            pointer_path = f"MooMooAU/State/processed-current/{bundle.source_id}.json.age"
            pointer_object = self._encrypt(
                pointer_path,
                ProcessedObjectRole.CURRENT_POINTER,
                pointer.to_bytes(),
            )
        return ProcessedCommitPlan(
            source_id=bundle.source_id,
            parser_name=bundle.parser_name,
            parser_version=bundle.parser_version,
            key_epoch=key_epoch,
            decision=decision,
            immutable_objects=tuple(objects),
            current_pointer=pointer_object,
            expected_pointer_revision=expected_pointer_revision,
        )

    def _encrypt(
        self,
        relative_path: str,
        role: ProcessedObjectRole,
        plaintext: bytes,
    ) -> PrivateProcessedObject:
        source = io.BytesIO(plaintext)
        sink = io.BytesIO()
        self._age.encrypt_stream(self._recipient, source, sink)
        ciphertext = sink.getvalue()
        return PrivateProcessedObject(
            relative_path=relative_path,
            role=role,
            plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
            ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            ciphertext=ciphertext,
        )


@dataclass(frozen=True, slots=True, repr=False)
class RevisionedCiphertext:
    ciphertext: bytes = field(repr=False)
    revision: str

    def __post_init__(self) -> None:
        if not is_age_envelope(self.ciphertext) or _GIT_REVISION.fullmatch(self.revision) is None:
            raise ProcessedCommitError("revisioned ciphertext is invalid")


class ProcessedCiphertextStore(Protocol):
    def fetch_immutable(self, relative_path: str) -> bytes | None: ...

    def append_immutable(self, relative_path: str, ciphertext: bytes) -> bool: ...

    def fetch_current(self, relative_path: str) -> RevisionedCiphertext | None: ...

    def compare_and_swap_current(
        self,
        relative_path: str,
        ciphertext: bytes,
        expected_revision: str | None,
    ) -> bool: ...


class MemoryProcessedCiphertextStore:
    """Synthetic remote with append-only objects and one CAS current value per source."""

    def __init__(self, fail_after_writes: int | None = None) -> None:
        self._immutable: dict[str, bytes] = {}
        self._current: dict[str, RevisionedCiphertext] = {}
        self._fail_after = fail_after_writes
        self.write_calls = 0
        self.fetch_calls = 0

    def fetch_immutable(self, relative_path: str) -> bytes | None:
        if (
            _PRIVATE_PATH.fullmatch(relative_path) is None
            or _CURRENT_PATH.fullmatch(relative_path) is not None
        ):
            raise ProcessedCommitError("synthetic Processed immutable path is invalid")
        self.fetch_calls += 1
        value = self._immutable.get(relative_path)
        return bytes(value) if value is not None else None

    def append_immutable(self, relative_path: str, ciphertext: bytes) -> bool:
        self._maybe_fail()
        if relative_path in self._immutable:
            return False
        if (
            _PRIVATE_PATH.fullmatch(relative_path) is None
            or _CURRENT_PATH.fullmatch(relative_path) is not None
            or not is_age_envelope(ciphertext)
        ):
            raise ProcessedCommitError("synthetic Processed store rejected immutable write")
        self._immutable[relative_path] = bytes(ciphertext)
        self.write_calls += 1
        return True

    def fetch_current(self, relative_path: str) -> RevisionedCiphertext | None:
        if _CURRENT_PATH.fullmatch(relative_path) is None:
            raise ProcessedCommitError("synthetic Processed current path is invalid")
        self.fetch_calls += 1
        value = self._current.get(relative_path)
        return (
            RevisionedCiphertext(bytes(value.ciphertext), value.revision)
            if value is not None
            else None
        )

    def compare_and_swap_current(
        self,
        relative_path: str,
        ciphertext: bytes,
        expected_revision: str | None,
    ) -> bool:
        self._maybe_fail()
        if _CURRENT_PATH.fullmatch(relative_path) is None or not is_age_envelope(ciphertext):
            raise ProcessedCommitError("synthetic Processed store rejected current write")
        incumbent = self._current.get(relative_path)
        actual_revision = incumbent.revision if incumbent is not None else None
        if actual_revision != expected_revision:
            return False
        revision = hashlib.sha1(ciphertext, usedforsecurity=False).hexdigest()
        self._current[relative_path] = RevisionedCiphertext(bytes(ciphertext), revision)
        self.write_calls += 1
        return True

    def immutable_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._immutable))

    def current_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._current))

    def ciphertexts(self) -> tuple[bytes, ...]:
        values = list(self._immutable.values())
        values.extend(item.ciphertext for item in self._current.values())
        return tuple(values)

    def _maybe_fail(self) -> None:
        if self._fail_after is not None and self.write_calls >= self._fail_after:
            raise ProcessedCommitError("synthetic Processed write failed")


class GitHubProcessedCiphertextStore:
    """Production-capable single-repository adapter; recovery remains a later gate."""

    def __init__(
        self,
        guard: GitHubEndpointGuard,
        locator: RepositoryLocator,
        token: InstallationToken,
    ) -> None:
        self._guard = guard
        self._locator = locator
        self._token = token

    def fetch_immutable(self, relative_path: str) -> bytes | None:
        if (
            _PRIVATE_PATH.fullmatch(relative_path) is None
            or _CURRENT_PATH.fullmatch(relative_path) is not None
        ):
            raise ProcessedCommitError("private Processed immutable path is invalid")
        response = self._guard.send(
            HttpRequest(
                "GET",
                content_url(self._locator, relative_path),
                headers=self._headers("application/vnd.github.raw+json"),
            )
        )
        if response.status == 404:
            return None
        if response.status != 200 or not is_age_envelope(response.body):
            raise ProcessedCommitError("private Processed read failed")
        return response.body

    def append_immutable(self, relative_path: str, ciphertext: bytes) -> bool:
        if (
            _PRIVATE_PATH.fullmatch(relative_path) is None
            or _CURRENT_PATH.fullmatch(relative_path) is not None
            or not is_age_envelope(ciphertext)
        ):
            raise ProcessedCommitError("private Processed append rejected input")
        body = _canonical_json(
            {
                "content": base64.b64encode(ciphertext).decode("ascii"),
                "message": CONTENT_APPEND_MESSAGE,
            }
        )
        response = self._guard.send(
            HttpRequest(
                "PUT",
                content_url(self._locator, relative_path),
                headers=self._headers("application/vnd.github+json"),
                body=body,
            )
        )
        if response.status == 201:
            return True
        if response.status in {409, 422}:
            return False
        raise ProcessedCommitError("private Processed append failed")

    def fetch_current(self, relative_path: str) -> RevisionedCiphertext | None:
        if _CURRENT_PATH.fullmatch(relative_path) is None:
            raise ProcessedCommitError("private Processed current path is invalid")
        response = self._guard.send(
            HttpRequest(
                "GET",
                content_url(self._locator, relative_path),
                headers=self._headers("application/vnd.github+json"),
            )
        )
        if response.status == 404:
            return None
        if response.status != 200:
            raise ProcessedCommitError("private Processed current read failed")
        try:
            value = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProcessedCommitError("private Processed current response is invalid") from exc
        if not isinstance(value, dict) or value.get("encoding") != "base64":
            raise ProcessedCommitError("private Processed current response is invalid")
        encoded = value.get("content")
        revision = value.get("sha")
        if not isinstance(encoded, str) or not isinstance(revision, str):
            raise ProcessedCommitError("private Processed current response is invalid")
        compact = encoded.replace("\n", "")
        if any(character.isspace() for character in compact):
            raise ProcessedCommitError("private Processed current base64 is invalid")
        try:
            ciphertext = base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ProcessedCommitError("private Processed current base64 is invalid") from exc
        return RevisionedCiphertext(ciphertext, revision)

    def compare_and_swap_current(
        self,
        relative_path: str,
        ciphertext: bytes,
        expected_revision: str | None,
    ) -> bool:
        if _CURRENT_PATH.fullmatch(relative_path) is None or not is_age_envelope(ciphertext):
            raise ProcessedCommitError("private Processed current write rejected input")
        payload: dict[str, object] = {
            "content": base64.b64encode(ciphertext).decode("ascii"),
            "message": CONTENT_POINTER_MESSAGE,
        }
        if expected_revision is not None:
            payload["sha"] = expected_revision
        response = self._guard.send(
            HttpRequest(
                "PUT",
                content_url(self._locator, relative_path),
                headers=self._headers("application/vnd.github+json"),
                body=_canonical_json(payload),
            )
        )
        if response.status in {200, 201}:
            return True
        if response.status in {409, 422}:
            return False
        raise ProcessedCommitError("private Processed current CAS failed")

    def _headers(self, accept: str) -> tuple[tuple[str, str], ...]:
        try:
            token = self._token.value.reveal()
        except Exception as exc:
            raise GitHubBoundaryError("installation token is unavailable") from exc
        return (
            ("Accept", accept),
            ("Authorization", "Bearer " + token),
            ("Content-Type", "application/json"),
            ("X-GitHub-Api-Version", GITHUB_API_VERSION),
        )


@dataclass(frozen=True, slots=True)
class ProcessedCommitResult:
    state: ProcessedCommitState
    created_count: int
    existing_count: int
    immutable_count: int
    current_pointer_updated: bool
    remote_recovery_verified: bool
    public_publish_eligible: bool
    m3_eligible: bool


class ProcessedCommitSaga:
    def __init__(self, store: ProcessedCiphertextStore) -> None:
        self._store = store

    def commit(self, plan: ProcessedCommitPlan) -> ProcessedCommitResult:
        created = 0
        existing = 0
        for item in plan.immutable_objects:
            remote = self._store.fetch_immutable(item.relative_path)
            if remote is not None:
                if not is_age_envelope(remote):
                    raise ProcessedCommitError("existing Processed object is not age encrypted")
                existing += 1
                continue
            if self._store.append_immutable(item.relative_path, item.ciphertext):
                created += 1
                continue
            raced = self._store.fetch_immutable(item.relative_path)
            if raced is None or not is_age_envelope(raced):
                raise ProcessedCommitError("Processed append conflict did not converge")
            existing += 1
        pointer_updated = False
        if plan.current_pointer is not None:
            pointer = plan.current_pointer
            incumbent = self._store.fetch_current(pointer.relative_path)
            if incumbent is not None and hmac.compare_digest(
                incumbent.ciphertext,
                pointer.ciphertext,
            ):
                pass
            else:
                actual_revision = incumbent.revision if incumbent is not None else None
                if actual_revision != plan.expected_pointer_revision:
                    raise ProcessedCommitError("Processed current pointer CAS precondition changed")
                pointer_updated = self._store.compare_and_swap_current(
                    pointer.relative_path,
                    pointer.ciphertext,
                    plan.expected_pointer_revision,
                )
                if not pointer_updated:
                    raise ProcessedCommitError("Processed current pointer CAS did not converge")
        state = (
            ProcessedCommitState.PRIVATE_PROCESSED_COMMITTED_RECOVERY_PENDING
            if plan.current_pointer is not None
            else ProcessedCommitState.CANDIDATE_COMMITTED_CURRENT_UNCHANGED
        )
        return ProcessedCommitResult(
            state=state,
            created_count=created,
            existing_count=existing,
            immutable_count=len(plan.immutable_objects),
            current_pointer_updated=pointer_updated,
            remote_recovery_verified=False,
            public_publish_eligible=False,
            m3_eligible=False,
        )


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ProcessedCommitError(f"private processed field {key} is invalid")
    return item


def _required_integer(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int:
        raise ProcessedCommitError(f"private processed field {key} is invalid")
    return item


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProcessedCommitError("protected approval timestamp is invalid") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ProcessedCommitError("protected approval timestamp must be UTC")
    return parsed.astimezone(UTC)


def _semver_key(value: str) -> tuple[int, int, int]:
    if _SEMVER.fullmatch(value) is None:
        raise ProcessedCommitError("parser version is invalid")
    values = tuple(int(item) for item in value.split("."))
    return cast(tuple[int, int, int], values)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
