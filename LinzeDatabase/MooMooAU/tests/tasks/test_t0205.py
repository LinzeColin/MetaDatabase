from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest

from moomooau_archive.age_stream import AgeStreamError, OfficialAgeStream, is_age_envelope
from moomooau_archive.recovery import AgeIdentityGenerator


class FailingSink(io.BytesIO):
    def write(self, value: bytes, /) -> int:
        del value
        raise RuntimeError("synthetic sink failure")


def test_t0205_streams_plaintext_through_official_age_without_plaintext_file() -> None:
    payload = b"synthetic-stream-block-" * 20_000
    cipher = OfficialAgeStream(chunk_size=4096)
    generated = AgeIdentityGenerator().generate()
    identity_path: Path
    try:
        with tempfile.TemporaryDirectory(prefix="moomooau-s2-age-") as directory:
            root = Path(directory)
            identity_path = root / "synthetic-identity.txt"
            identity_path.write_bytes(generated.identity.reveal())
            identity_path.chmod(0o600)
            encrypted = io.BytesIO()
            cipher.encrypt_stream(generated.recipient, io.BytesIO(payload), encrypted)
            ciphertext = encrypted.getvalue()
            assert is_age_envelope(ciphertext)
            assert payload[:256] not in ciphertext

            recovered = io.BytesIO()
            cipher.decrypt_stream(
                identity_path,
                io.BytesIO(ciphertext),
                recovered,
                allowed_tmpfs_roots=(root,),
            )
            assert recovered.getvalue() == payload
        assert not identity_path.exists()
    finally:
        generated.destroy()


def test_t0205_rejects_identity_outside_approved_ephemeral_root() -> None:
    generated = AgeIdentityGenerator().generate()
    try:
        with tempfile.TemporaryDirectory(prefix="moomooau-s2-age-") as directory:
            root = Path(directory)
            identity_path = root / "synthetic-identity.txt"
            identity_path.write_bytes(generated.identity.reveal())
            identity_path.chmod(0o600)
            with pytest.raises(AgeStreamError, match="outside"):
                OfficialAgeStream().decrypt_stream(
                    identity_path,
                    io.BytesIO(b"not-an-envelope"),
                    io.BytesIO(),
                    allowed_tmpfs_roots=(root / "different-root",),
                )
    finally:
        generated.destroy()


def test_t0205_kills_age_process_and_redacts_sink_failure() -> None:
    generated = AgeIdentityGenerator().generate()
    try:
        with pytest.raises(AgeStreamError, match="redacted diagnostics") as error:
            OfficialAgeStream(chunk_size=4096).encrypt_stream(
                generated.recipient,
                io.BytesIO(b"synthetic" * 100_000),
                FailingSink(),
            )
        assert "synthetic sink failure" not in str(error.value)
    finally:
        generated.destroy()
