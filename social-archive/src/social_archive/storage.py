from __future__ import annotations

import mimetypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .utils import atomic_write, sha256_bytes, sha256_file


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    byte_size: int
    path: Path
    media_type: str | None


class RemoteEncryptedObject(Protocol):
    original_sha256: str
    cipher_sha256: str
    original_byte_size: int
    cipher_byte_size: int
    path: Path
    media_type: str | None
    algorithm: str


def create_s3_client(
    *,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    region_name: str = "auto",
    addressing_style: str = "path",
    s3_compatibility: str = "aws",
):
    """Build an S3 client for a verified encrypted replica destination.

    OCI's S3 compatibility endpoint rejects AWS chunked payload encoding. Its
    provider mode keeps HTTPS transport authentication while avoiding optional
    streamed checksums; every Social Archive ciphertext remains bound to its
    SHA-256 metadata and mandatory readback hash.
    """
    import boto3
    from botocore.config import Config

    if addressing_style not in {"auto", "path", "virtual"}:
        raise ValueError("S3 addressing_style 只能是 auto、path 或 virtual")
    if s3_compatibility not in {"aws", "oci"}:
        raise ValueError("S3 compatibility 只能是 aws 或 oci")

    s3_options: dict[str, object] = {"addressing_style": addressing_style}
    config_options: dict[str, object] = {"s3": s3_options}
    if s3_compatibility == "oci":
        s3_options["payload_signing_enabled"] = False
        config_options["request_checksum_calculation"] = "when_required"
        config_options["response_checksum_validation"] = "when_required"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
        config=Config(**config_options),
    )


class ContentAddressedStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str, suffix: str = "") -> Path:
        clean_suffix = suffix if suffix.startswith(".") and len(suffix) <= 16 else ""
        return self.root / "sha256" / digest[:2] / digest[2:4] / f"{digest}{clean_suffix}"

    def put_bytes(self, data: bytes, *, suffix: str = "", media_type: str | None = None) -> StoredObject:
        digest = sha256_bytes(data)
        path = self._path(digest, suffix)
        if not path.exists():
            atomic_write(path, data)
        elif sha256_file(path) != digest:
            raise RuntimeError(f"内容寻址冲突：{path}")
        return StoredObject(digest, len(data), path, media_type or mimetypes.guess_type(path.name)[0])

    def import_file(self, source: Path, *, media_type: str | None = None) -> StoredObject:
        source = source.resolve(strict=True)
        if not source.is_file() or source.is_symlink():
            raise ValueError("只能导入普通文件")
        digest = sha256_file(source)
        suffix = source.suffix if len(source.suffix) <= 16 else ""
        target = self._path(digest, suffix)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            shutil.copyfile(source, tmp)
            if sha256_file(tmp) != digest:
                tmp.unlink(missing_ok=True)
                raise RuntimeError("复制后哈希不一致")
            os.chmod(tmp, 0o640)
            os.replace(tmp, target)
        return StoredObject(digest, source.stat().st_size, target, media_type or mimetypes.guess_type(source.name)[0])


class S3ReplicaStore:
    """S3-compatible encrypted replica store for R2 or OCI.

    This class accepts only an object that exposes original and ciphertext hashes.
    Passing plaintext ``StoredObject`` is intentionally rejected at runtime.
    """

    def __init__(
        self,
        *,
        store_id: str,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str,
        region_name: str = "auto",
        addressing_style: str = "path",
        s3_compatibility: str = "aws",
    ):
        self.store_id = store_id
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.s3_compatibility = s3_compatibility
        self.client = create_s3_client(
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region_name=region_name,
            addressing_style=addressing_style,
            s3_compatibility=s3_compatibility,
        )

    def object_key(self, original_digest: str) -> str:
        return f"{self.prefix}/sha256/{original_digest[:2]}/{original_digest[2:4]}/{original_digest}.age"

    def put_encrypted(self, obj: RemoteEncryptedObject) -> tuple[str, str | None]:
        if not obj.path.name.endswith(".age") or sha256_file(obj.path) != obj.cipher_sha256:
            raise RuntimeError("只允许上传已校验的 age 密文")
        key = self.object_key(obj.original_sha256)
        metadata = {
            "original-sha256": obj.original_sha256,
            "cipher-sha256": obj.cipher_sha256,
            "encryption": obj.algorithm,
        }
        extra_args: dict[str, object] = {"Metadata": metadata}
        if self.s3_compatibility == "aws":
            extra_args["StorageClass"] = "STANDARD"
        self.client.upload_file(str(obj.path), self.bucket, key, ExtraArgs=extra_args)
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        remote = head.get("Metadata") or {}
        if (
            remote.get("original-sha256") != obj.original_sha256
            or remote.get("cipher-sha256") != obj.cipher_sha256
            or remote.get("encryption") != obj.algorithm
        ):
            raise RuntimeError(f"{self.store_id} 密文元数据校验失败")
        return key, str(head.get("ETag", "")).strip('"') or None

    def download_verified(self, key: str, target: Path, expected_cipher_sha256: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.download")
        self.client.download_file(self.bucket, key, str(tmp))
        if sha256_file(tmp) != expected_cipher_sha256:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"{self.store_id} 密文回读哈希不一致")
        os.replace(tmp, target)
