"""Side-effect ports; core verification remains pure and dependency-injected."""

from __future__ import annotations

from typing import Protocol

from .models import CandidateMetadata


class RawMessageSource(Protocol):
    def discover(self) -> tuple[CandidateMetadata, ...]: ...

    def get_raw(self, source_id: str) -> bytes: ...


class CiphertextStore(Protocol):
    def put(self, object_name: str, ciphertext: bytes) -> None: ...

    def fetch(self, object_name: str) -> bytes: ...


class AgeCipher(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> bytes: ...
