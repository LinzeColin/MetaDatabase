from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .storage import StoredObject
from .utils import atomic_write, sha256_bytes, sha256_file


@dataclass(frozen=True)
class EncryptedObject:
    """One reusable age ciphertext for all remote replicas of an artifact."""

    original_sha256: str
    cipher_sha256: str
    original_byte_size: int
    cipher_byte_size: int
    path: Path
    media_type: str | None
    algorithm: str = "age-x25519"


class AgeEncryptor:
    """Encrypt once and reuse the exact ciphertext for R2, OCI and GitHub.

    Normal replication needs only the public age recipient. The private identity is
    required solely for an explicit restore drill and is never read by this class.
    """

    def __init__(
        self,
        *,
        recipient: str,
        root: Path,
        binary: str = "age",
        runner: Callable[[Sequence[str]], None] | None = None,
    ):
        recipient = recipient.strip()
        if not recipient:
            raise ValueError("缺少 SOCIAL_ARCHIVE_AGE_RECIPIENT")
        self.recipient = recipient
        self.root = root.resolve()
        self.binary = binary
        self._runner = runner or self._run
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def recipient_fingerprint(self) -> str:
        return sha256_bytes(self.recipient.encode("utf-8"))[:24]

    def _run(self, argv: Sequence[str]) -> None:
        resolved = shutil.which(argv[0])
        if not resolved:
            raise RuntimeError("缺少 age 命令，不能把明文上传到远端")
        command = [resolved, *argv[1:]]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode:
            raise RuntimeError((completed.stderr or completed.stdout or "age 加密失败")[-1500:])

    def _paths(self, original_sha256: str) -> tuple[Path, Path]:
        folder = self.root / "sha256" / original_sha256[:2] / original_sha256[2:4]
        return folder / f"{original_sha256}.age", folder / f"{original_sha256}.age.json"

    def encrypt(self, obj: StoredObject) -> EncryptedObject:
        if sha256_file(obj.path) != obj.sha256:
            raise RuntimeError("本地对象哈希与登记值不一致，已拒绝加密")
        cipher, manifest = self._paths(obj.sha256)
        if cipher.is_file() and manifest.is_file():
            try:
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
                cipher_sha = sha256_file(cipher)
                if (
                    metadata.get("original_sha256") == obj.sha256
                    and metadata.get("cipher_sha256") == cipher_sha
                    and metadata.get("recipient_fingerprint") == self.recipient_fingerprint
                ):
                    return EncryptedObject(
                        original_sha256=obj.sha256,
                        cipher_sha256=cipher_sha,
                        original_byte_size=obj.byte_size,
                        cipher_byte_size=cipher.stat().st_size,
                        path=cipher,
                        media_type=obj.media_type,
                    )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            cipher.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)

        cipher.parent.mkdir(parents=True, exist_ok=True)
        tmp = cipher.with_name(f".{cipher.name}.{os.getpid()}.tmp")
        tmp.unlink(missing_ok=True)
        self._runner([self.binary, "-r", self.recipient, "-o", str(tmp), str(obj.path)])
        if not tmp.is_file() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("age 未产生有效密文")
        os.chmod(tmp, 0o600)
        os.replace(tmp, cipher)
        cipher_sha = sha256_file(cipher)
        metadata = {
            "schema_version": "1.0",
            "algorithm": "age-x25519",
            "recipient_fingerprint": self.recipient_fingerprint,
            "original_sha256": obj.sha256,
            "original_byte_size": obj.byte_size,
            "cipher_sha256": cipher_sha,
            "cipher_byte_size": cipher.stat().st_size,
        }
        atomic_write(manifest, (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        return EncryptedObject(
            original_sha256=obj.sha256,
            cipher_sha256=cipher_sha,
            original_byte_size=obj.byte_size,
            cipher_byte_size=cipher.stat().st_size,
            path=cipher,
            media_type=obj.media_type,
        )
