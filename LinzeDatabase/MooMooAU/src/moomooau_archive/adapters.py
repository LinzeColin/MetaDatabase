"""Synthetic-only adapters, including the official age CLI boundary."""

from __future__ import annotations

import base64
import binascii
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import TracebackType

from .models import CandidateMetadata, SyntheticMessage

AGE_HEADER = b"age-encryption.org/v1"


def is_age_envelope(value: bytes) -> bool:
    """Recognize the pinned single-X25519 age v1 binary envelope structure."""

    lines: list[bytes] = []
    start = 0
    for _ in range(4):
        end = value.find(b"\n", start)
        if end < 0:
            return False
        lines.append(value[start:end])
        start = end + 1
    version, stanza, wrapped_key, footer = lines
    if (
        version != AGE_HEADER
        or not stanza.startswith(b"-> X25519 ")
        or not footer.startswith(b"--- ")
        or len(value) - start < 32
    ):
        return False
    encoded_ephemeral = stanza.removeprefix(b"-> X25519 ")
    encoded_mac = footer.removeprefix(b"--- ")
    return all(
        _is_canonical_base64_32(item) for item in (encoded_ephemeral, wrapped_key, encoded_mac)
    )


def _is_canonical_base64_32(value: bytes) -> bool:
    if len(value) != 43:
        return False
    try:
        decoded = base64.b64decode(value + b"=", validate=True)
    except (ValueError, binascii.Error):
        return False
    return len(decoded) == 32 and base64.b64encode(decoded).rstrip(b"=") == value


class AgeUnavailable(RuntimeError):
    pass


class AgeOperationError(RuntimeError):
    pass


class TrackedSyntheticSource:
    def __init__(self, messages: tuple[SyntheticMessage, ...]) -> None:
        self._messages = {message.metadata.source_id: message for message in messages}
        self.raw_fetches: list[str] = []

    def discover(self) -> tuple[CandidateMetadata, ...]:
        return tuple(message.metadata for message in self._messages.values())

    def get_raw(self, source_id: str) -> bytes:
        self.raw_fetches.append(source_id)
        return self._messages[source_id].raw


class MemoryCiphertextStore:
    """Ephemeral stand-in for the future single private GitHub database."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.put_calls = 0
        self.fetch_calls = 0

    def put(self, object_name: str, ciphertext: bytes) -> None:
        if not object_name.endswith(".age"):
            raise ValueError("ciphertext object must use the .age suffix")
        if not is_age_envelope(ciphertext):
            raise ValueError("object is not an age envelope")
        self._objects[object_name] = bytes(ciphertext)
        self.put_calls += 1

    def fetch(self, object_name: str) -> bytes:
        self.fetch_calls += 1
        return bytes(self._objects[object_name])

    def object_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._objects))

    def ciphertexts(self) -> tuple[bytes, ...]:
        return tuple(self._objects[name] for name in sorted(self._objects))


class EphemeralAgeSession:
    """Official age CLI with an ephemeral synthetic identity and stdin plaintext."""

    def __init__(self, age_binary: str | None = None, keygen_binary: str | None = None) -> None:
        self._age_binary = age_binary or shutil.which("age")
        self._keygen_binary = keygen_binary or shutil.which("age-keygen")
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._identity_path: Path | None = None
        self._recipient: str | None = None

    def __enter__(self) -> EphemeralAgeSession:
        if self._age_binary is None or self._keygen_binary is None:
            raise AgeUnavailable("official age and age-keygen binaries are required")
        self._temporary = tempfile.TemporaryDirectory(prefix="moomooau-age-synthetic-")
        self._identity_path = Path(self._temporary.name) / "synthetic-identity.txt"
        completed = subprocess.run(
            [self._keygen_binary, "-o", str(self._identity_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            self._cleanup()
            raise AgeOperationError("age-keygen failed with redacted diagnostics")
        marker = "Public key: "
        recipient = next(
            (
                line.removeprefix(marker).strip()
                for line in completed.stderr.splitlines()
                if line.startswith(marker)
            ),
            None,
        )
        if not recipient or not recipient.startswith("age1"):
            self._cleanup()
            raise AgeOperationError("age-keygen returned no usable public recipient")
        self._recipient = recipient
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
        self._temporary = None
        self._identity_path = None
        self._recipient = None

    def _require_ready(self) -> tuple[str, str, Path]:
        if self._age_binary is None or self._recipient is None or self._identity_path is None:
            raise AgeOperationError("age session is not active")
        return self._age_binary, self._recipient, self._identity_path

    def encrypt(self, plaintext: bytes) -> bytes:
        age_binary, recipient, _ = self._require_ready()
        completed = subprocess.run(
            [age_binary, "--encrypt", "--recipient", recipient],
            input=plaintext,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise AgeOperationError("age encryption failed with redacted diagnostics")
        return completed.stdout

    def decrypt(self, ciphertext: bytes) -> bytes:
        age_binary, _, identity_path = self._require_ready()
        completed = subprocess.run(
            [age_binary, "--decrypt", "--identity", str(identity_path)],
            input=ciphertext,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise AgeOperationError("age decryption failed with redacted diagnostics")
        return completed.stdout
