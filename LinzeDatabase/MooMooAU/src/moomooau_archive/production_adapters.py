"""Production-only age crypto and immutable first-import recovery adapters.

Both adapters operate on injected, already-guarded ports.  They perform no environment
discovery and never persist plaintext.  ``RemoteFirstImportTimestampSource`` treats an absent
current pointer as the first import; every other absence, mismatch or corrupt ciphertext is a
fail-closed error.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
from datetime import UTC, datetime, timedelta
from typing import cast

from .age_stream import OfficialAgeStream, is_age_envelope
from .processed_commit import CurrentProcessedPointer, ProcessedCiphertextStore
from .remote_recovery_gate import CiphertextDecryptor

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_ENVELOPE_BYTES = 16 * 1024 * 1024


class ProductionAdapterError(RuntimeError):
    """A production adapter failed without exposing protected values."""


class OfficialAgeCrypto:
    """Encrypt with the configured recipient and decrypt with the protected identity."""

    def __init__(
        self,
        age: OfficialAgeStream,
        recipient: str,
        decryptor: CiphertextDecryptor,
    ) -> None:
        if not recipient:
            raise ProductionAdapterError("age crypto recipient is invalid")
        self._age = age
        self._recipient = recipient
        self._decryptor = decryptor

    def encrypt(self, plaintext: bytes) -> bytes:
        if not isinstance(plaintext, bytes):
            raise ProductionAdapterError("age crypto plaintext is invalid")
        source = io.BytesIO(plaintext)
        sink = io.BytesIO()
        try:
            self._age.encrypt_stream(self._recipient, source, sink)
        except Exception as exc:
            raise ProductionAdapterError("age encryption failed") from exc
        ciphertext = sink.getvalue()
        if not is_age_envelope(ciphertext):
            raise ProductionAdapterError("age encryption returned no valid envelope")
        return ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        if not is_age_envelope(ciphertext):
            raise ProductionAdapterError("age decryption input is invalid")
        try:
            return self._decryptor.decrypt(ciphertext)
        except Exception as exc:
            raise ProductionAdapterError("age decryption failed") from exc


class RemoteFirstImportTimestampSource:
    """Recover the immutable first-import timestamp from current Processed lineage."""

    def __init__(
        self,
        store: ProcessedCiphertextStore,
        decryptor: CiphertextDecryptor,
    ) -> None:
        self._store = store
        self._decryptor = decryptor

    def resolve(self, source_id: str, observed_at_utc: datetime) -> datetime:
        if _SHA256.fullmatch(source_id) is None or not _is_utc(observed_at_utc):
            raise ProductionAdapterError("first-import lookup input is invalid")
        pointer_path = f"MooMooAU/State/processed-current/{source_id}.json.age"
        revisioned = self._store.fetch_current(pointer_path)
        if revisioned is None:
            return observed_at_utc.astimezone(UTC)
        try:
            pointer_plaintext = self._decryptor.decrypt(revisioned.ciphertext)
            pointer = CurrentProcessedPointer.from_bytes(pointer_plaintext)
        except Exception as exc:
            raise ProductionAdapterError("current Processed pointer recovery failed") from exc
        if pointer.source_id != source_id:
            raise ProductionAdapterError("current Processed pointer source differs")

        manifest_ciphertext = self._store.fetch_immutable(pointer.manifest_path)
        if manifest_ciphertext is None:
            raise ProductionAdapterError("current Processed manifest is unavailable")
        try:
            manifest_plaintext = self._decryptor.decrypt(manifest_ciphertext)
            manifest = _decode_object(manifest_plaintext, maximum=_MAX_MANIFEST_BYTES)
        except Exception as exc:
            raise ProductionAdapterError("current Processed manifest recovery failed") from exc
        artifact = _validate_manifest(pointer, manifest)

        relative_path = _required_string(artifact, "relative_path")
        envelope_ciphertext = self._store.fetch_immutable(relative_path)
        if envelope_ciphertext is None:
            raise ProductionAdapterError("current document envelope is unavailable")
        if not hmac.compare_digest(
            hashlib.sha256(envelope_ciphertext).hexdigest(),
            _required_string(artifact, "ciphertext_sha256"),
        ):
            raise ProductionAdapterError("current document envelope ciphertext differs")
        try:
            envelope_plaintext = self._decryptor.decrypt(envelope_ciphertext)
        except Exception as exc:
            raise ProductionAdapterError("current document envelope recovery failed") from exc
        if not hmac.compare_digest(
            hashlib.sha256(envelope_plaintext).hexdigest(),
            _required_string(artifact, "plaintext_sha256"),
        ):
            raise ProductionAdapterError("current document envelope plaintext differs")
        envelope = _decode_jsonl_object(envelope_plaintext)
        lineage = envelope.get("lineage")
        if (
            set(envelope)
            != {
                "schema_version",
                "source_id",
                "document_class",
                "classification",
                "verification",
                "gmail",
                "attachments",
                "processing_state",
                "processing_reason",
                "lineage",
            }
            or envelope.get("source_id") != source_id
            or not isinstance(lineage, dict)
            or lineage.get("source_id") != source_id
        ):
            raise ProductionAdapterError("current document envelope binding differs")
        imported = _parse_utc(lineage.get("imported_at_utc"))
        if imported > observed_at_utc:
            raise ProductionAdapterError("first-import timestamp is after the observation")
        return imported


def _validate_manifest(
    pointer: CurrentProcessedPointer,
    value: dict[str, object],
) -> dict[str, object]:
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
    artifacts = value.get("artifacts")
    if (
        set(value) != required
        or value.get("schema_version") != "moomooau.private-processed-manifest.v1"
        or value.get("source_id") != pointer.source_id
        or value.get("parser_name") != pointer.parser_name
        or value.get("parser_version") != pointer.parser_version
        or value.get("output_schema_version") != pointer.schema_version
        or value.get("business_root") != pointer.business_root
        or value.get("snapshot_root") != pointer.snapshot_root
        or value.get("key_epoch") != pointer.key_epoch
        or not isinstance(artifacts, list)
    ):
        raise ProductionAdapterError("current Processed manifest binding differs")
    matches: list[dict[str, object]] = []
    paths: list[str] = []
    for raw in artifacts:
        if not isinstance(raw, dict) or set(raw) != {
            "dataset_name",
            "format",
            "relative_path",
            "plaintext_sha256",
            "ciphertext_sha256",
            "schema_version",
        }:
            raise ProductionAdapterError("current Processed artifact schema is invalid")
        artifact = cast(dict[str, object], raw)
        path = _required_string(artifact, "relative_path")
        paths.append(path)
        for digest_name in ("plaintext_sha256", "ciphertext_sha256"):
            if _SHA256.fullmatch(_required_string(artifact, digest_name)) is None:
                raise ProductionAdapterError("current Processed artifact digest is invalid")
        if artifact.get("dataset_name") == "document_envelopes":
            if artifact.get("format") != "JSONL":
                raise ProductionAdapterError("current document envelope format is invalid")
            matches.append(artifact)
    if len(paths) != len(set(paths)) or len(matches) != 1:
        raise ProductionAdapterError("current document envelope identity is ambiguous")
    return matches[0]


def _decode_object(payload: bytes, *, maximum: int) -> dict[str, object]:
    if not payload or len(payload) > maximum:
        raise ProductionAdapterError("protected JSON object exceeds its byte contract")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionAdapterError("protected JSON object is invalid") from exc
    if not isinstance(value, dict):
        raise ProductionAdapterError("protected JSON value is not an object")
    return cast(dict[str, object], value)


def _decode_jsonl_object(payload: bytes) -> dict[str, object]:
    if not payload or len(payload) > _MAX_ENVELOPE_BYTES or not payload.endswith(b"\n"):
        raise ProductionAdapterError("document envelope JSONL is invalid")
    body = payload[:-1]
    if not body or b"\n" in body or b"\r" in body:
        raise ProductionAdapterError("document envelope JSONL is not one canonical record")
    value = _decode_object(body, maximum=_MAX_ENVELOPE_BYTES)
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if canonical != body:
        raise ProductionAdapterError("document envelope JSONL is not canonical")
    return value


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ProductionAdapterError("protected string field is invalid")
    return item


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProductionAdapterError("first-import timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProductionAdapterError("first-import timestamp is invalid") from exc
    if not _is_utc(parsed) or parsed.isoformat().replace("+00:00", "Z") != value:
        raise ProductionAdapterError("first-import timestamp is invalid")
    return parsed.astimezone(UTC)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)
