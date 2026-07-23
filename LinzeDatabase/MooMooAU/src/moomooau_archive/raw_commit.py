"""Content-addressed, age-only, append-only private Raw commit boundary."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from .age_stream import OfficialAgeStream, is_age_envelope
from .attachment_inspector import AttachmentInspectionReport
from .canonical_raw import CanonicalRaw
from .github_guard import (
    CONTENT_APPEND_MESSAGE,
    GITHUB_API_VERSION,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    InstallationToken,
    RepositoryLocator,
    content_url,
)
from .http_boundary import HttpRequest
from .secret_values import SecretBytes

_OPAQUE_ID = re.compile(r"^[0-9a-f]{64}$")
_PRIVATE_PATH = re.compile(r"^MooMooAU/[A-Za-z0-9._/-]+\.age$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class RawCommitError(RuntimeError):
    """Private Raw planning or commit failed with redacted diagnostics."""


class RawObjectRole(StrEnum):
    MESSAGE = "MESSAGE"
    ATTACHMENT = "ATTACHMENT"
    MANIFEST = "MANIFEST"


class RawCommitState(StrEnum):
    PRIVATE_COMMITTED_RECOVERY_PENDING = "PRIVATE_COMMITTED_RECOVERY_PENDING"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateCiphertextObject:
    relative_path: str
    role: RawObjectRole
    plaintext_sha256: str
    ciphertext_sha256: str
    ciphertext: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            _PRIVATE_PATH.fullmatch(self.relative_path) is None
            or not self.relative_path.endswith(".age")
            or not is_age_envelope(self.ciphertext)
            or hashlib.sha256(self.ciphertext).hexdigest() != self.ciphertext_sha256
            or re.fullmatch(r"[0-9a-f]{64}", self.plaintext_sha256) is None
        ):
            raise RawCommitError("private ciphertext object is invalid")

    def __repr__(self) -> str:
        return (
            f"PrivateCiphertextObject(relative_path=<redacted>, role={self.role.value!r}, "
            "plaintext_sha256=<redacted>, ciphertext_sha256=<redacted>, "
            "ciphertext_bytes=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class RawCommitPlan:
    opaque_message_id: str
    content_id: str
    key_epoch: str
    objects: tuple[PrivateCiphertextObject, ...]

    def __post_init__(self) -> None:
        if (
            _OPAQUE_ID.fullmatch(self.opaque_message_id) is None
            or _OPAQUE_ID.fullmatch(self.content_id) is None
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or not self.objects
            or self.objects[-1].role is not RawObjectRole.MANIFEST
            or sum(item.role is RawObjectRole.MESSAGE for item in self.objects) != 1
            or sum(item.role is RawObjectRole.MANIFEST for item in self.objects) != 1
            or len({item.relative_path for item in self.objects}) != len(self.objects)
        ):
            raise RawCommitError("Raw commit plan is invalid")

    def __repr__(self) -> str:
        return (
            "RawCommitPlan(opaque_message_id=<redacted>, content_id=<redacted>, "
            f"key_epoch={self.key_epoch!r}, object_count={len(self.objects)})"
        )


@dataclass(frozen=True, slots=True)
class RawCommitResult:
    state: RawCommitState
    created_count: int
    existing_count: int
    object_count: int
    remote_recovery_verified: bool
    public_publish_eligible: bool
    m3_eligible: bool


class OpaqueIdFactory:
    """HMAC domain separation prevents public enumeration of Gmail IDs and hashes."""

    def __init__(self, key: SecretBytes) -> None:
        if len(key.reveal()) < 32:
            raise RawCommitError("opaque ID key is too short")
        self._key = key

    def message_id(self, gmail_message_id: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,256}", gmail_message_id) is None:
            raise RawCommitError("Gmail message ID is invalid")
        return self._digest(b"message-id\x00" + gmail_message_id.encode("ascii"))

    def content_id(self, plaintext_sha256: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", plaintext_sha256) is None:
            raise RawCommitError("plaintext digest is invalid")
        return self._digest(b"raw-content\x00" + bytes.fromhex(plaintext_sha256))

    def attachment_id(self, plaintext_sha256: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", plaintext_sha256) is None:
            raise RawCommitError("attachment digest is invalid")
        return self._digest(b"attachment-content\x00" + bytes.fromhex(plaintext_sha256))

    def _digest(self, value: bytes) -> str:
        return hmac.digest(self._key.reveal(), value, "sha256").hex()


class RawCommitPlanner:
    def __init__(
        self,
        age: OfficialAgeStream,
        recipient: str,
        opaque_ids: OpaqueIdFactory,
    ) -> None:
        self._age = age
        self._recipient = recipient
        self._opaque_ids = opaque_ids

    def plan(
        self,
        canonical: CanonicalRaw,
        attachments: AttachmentInspectionReport,
        *,
        key_epoch: str,
    ) -> RawCommitPlan:
        if _KEY_EPOCH.fullmatch(key_epoch) is None:
            raise RawCommitError("key epoch is invalid")
        if attachments.canonical_plaintext_sha256 != canonical.plaintext_sha256:
            raise RawCommitError("attachment report does not belong to Canonical Raw")
        opaque_message_id = self._opaque_ids.message_id(canonical.message_id)
        content_id = self._opaque_ids.content_id(canonical.plaintext_sha256)
        received = datetime.fromtimestamp(canonical.internal_date_ms / 1000, tz=UTC)
        message_path = (
            f"MooMooAU/Raw/messages/{received.year:04d}/{received.month:02d}/"
            f"{opaque_message_id}.eml.age"
        )
        objects: list[PrivateCiphertextObject] = [
            self._encrypt_object(message_path, RawObjectRole.MESSAGE, canonical.data)
        ]
        attachment_manifest: list[dict[str, object]] = []
        unique_attachments: dict[str, bytes] = {}
        for item in attachments.attachments:
            attachment_id: str | None = None
            if item.content is not None and item.plaintext_sha256 is not None:
                attachment_id = self._opaque_ids.attachment_id(item.plaintext_sha256)
                unique_attachments.setdefault(attachment_id, item.content)
            attachment_manifest.append(
                {
                    "attachment_object_id": attachment_id,
                    "byte_count": item.byte_count,
                    "decision": item.decision.value,
                    "declared_content_type": item.declared_content_type,
                    "filename": item.filename,
                    "kind": item.kind.value,
                    "ordinal": item.ordinal,
                    "plaintext_sha256": item.plaintext_sha256,
                    "reason_code": item.reason_code,
                }
            )
        for attachment_id in sorted(unique_attachments):
            path = f"MooMooAU/Raw/objects/{attachment_id[:2]}/{attachment_id}.bin.age"
            objects.append(
                self._encrypt_object(
                    path,
                    RawObjectRole.ATTACHMENT,
                    unique_attachments[attachment_id],
                )
            )
        manifest = {
            "schema_version": "moomooau.private-raw-manifest.v1",
            "attachment_inspection": {
                "message_quarantined": attachments.message_quarantined,
                "message_reason_code": attachments.message_reason_code,
                "parts_seen": attachments.parts_seen,
                "total_decoded_bytes": attachments.total_decoded_bytes,
            },
            "attachments": attachment_manifest,
            "content_id": content_id,
            "internal_date_ms": canonical.internal_date_ms,
            "key_epoch": key_epoch,
            "opaque_message_id": opaque_message_id,
            "raw_byte_count": canonical.byte_count,
            "raw_plaintext_sha256": canonical.plaintext_sha256,
            "raw_relative_path": message_path,
        }
        manifest_bytes = _canonical_json(manifest)
        manifest_path = f"MooMooAU/Manifests/raw/{opaque_message_id}.json.age"
        objects.append(self._encrypt_object(manifest_path, RawObjectRole.MANIFEST, manifest_bytes))
        return RawCommitPlan(opaque_message_id, content_id, key_epoch, tuple(objects))

    def _encrypt_object(
        self,
        path: str,
        role: RawObjectRole,
        plaintext: bytes,
    ) -> PrivateCiphertextObject:
        source = io.BytesIO(plaintext)
        sink = io.BytesIO()
        self._age.encrypt_stream(self._recipient, source, sink)
        ciphertext = sink.getvalue()
        if not is_age_envelope(ciphertext):
            raise RawCommitError("age encryption returned no valid envelope")
        return PrivateCiphertextObject(
            relative_path=path,
            role=role,
            plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
            ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            ciphertext=ciphertext,
        )


class AppendOnlyCiphertextStore(Protocol):
    def fetch(self, relative_path: str) -> bytes | None: ...

    def create(self, relative_path: str, ciphertext: bytes) -> bool: ...


class MemoryAppendOnlyCiphertextStore:
    """Synthetic remote: creation is allowed, replacement is impossible."""

    def __init__(self, fail_after_creates: int | None = None) -> None:
        self._objects: dict[str, bytes] = {}
        self._fail_after = fail_after_creates
        self.create_calls = 0
        self.fetch_calls = 0

    def fetch(self, relative_path: str) -> bytes | None:
        self.fetch_calls += 1
        value = self._objects.get(relative_path)
        return bytes(value) if value is not None else None

    def create(self, relative_path: str, ciphertext: bytes) -> bool:
        if self._fail_after is not None and self.create_calls >= self._fail_after:
            raise RawCommitError("synthetic private write failed")
        if relative_path in self._objects:
            return False
        if not is_age_envelope(ciphertext):
            raise RawCommitError("private store rejected plaintext")
        self._objects[relative_path] = bytes(ciphertext)
        self.create_calls += 1
        return True

    def object_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._objects))

    def ciphertexts(self) -> tuple[bytes, ...]:
        return tuple(self._objects[key] for key in sorted(self._objects))


class GitHubAppendOnlyCiphertextStore:
    """Production-capable adapter; callers still require a later Recovery Gate."""

    def __init__(
        self,
        guard: GitHubEndpointGuard,
        locator: RepositoryLocator,
        token: InstallationToken,
    ) -> None:
        self._guard = guard
        self._locator = locator
        self._token = token

    def fetch(self, relative_path: str) -> bytes | None:
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
            raise RawCommitError("private Contents read failed or returned non-age data")
        return response.body

    def create(self, relative_path: str, ciphertext: bytes) -> bool:
        if not is_age_envelope(ciphertext):
            raise RawCommitError("private Contents write rejected plaintext")
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
        raise RawCommitError("private Contents append failed")

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


class RawCommitSaga:
    def __init__(self, store: AppendOnlyCiphertextStore) -> None:
        self._store = store

    def commit(self, plan: RawCommitPlan) -> RawCommitResult:
        created = 0
        existing = 0
        for item in plan.objects:
            remote = self._store.fetch(item.relative_path)
            if remote is not None:
                if not is_age_envelope(remote):
                    raise RawCommitError("existing private object is not an age envelope")
                existing += 1
                continue
            was_created = self._store.create(item.relative_path, item.ciphertext)
            if was_created:
                created += 1
                continue
            raced = self._store.fetch(item.relative_path)
            if raced is None or not is_age_envelope(raced):
                raise RawCommitError("append-only create conflict did not converge")
            existing += 1
        return RawCommitResult(
            state=RawCommitState.PRIVATE_COMMITTED_RECOVERY_PENDING,
            created_count=created,
            existing_count=existing,
            object_count=len(plan.objects),
            remote_recovery_verified=False,
            public_publish_eligible=False,
            m3_eligible=False,
        )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
