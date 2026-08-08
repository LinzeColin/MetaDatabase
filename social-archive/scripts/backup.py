from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.encryption import AgeEncryptor, EncryptedObject
from social_archive.private_facts import delivered_completed_content_facts, fact_bytes, fact_sha256
from social_archive.storage import StoredObject, create_s3_client
from social_archive.utils import atomic_write, json_bytes, read_secret, sha256_bytes, sha256_file, utcnow


def _s3_config(store_id: str) -> dict[str, str] | None:
    prefix = f"SOCIAL_ARCHIVE_{store_id.upper()}"
    endpoint = os.getenv(f"{prefix}_ENDPOINT", "").strip()
    bucket = os.getenv(f"{prefix}_BUCKET", "").strip()
    access = read_secret(os.getenv(f"{prefix}_ACCESS_KEY_ID_FILE"))
    secret = read_secret(os.getenv(f"{prefix}_SECRET_ACCESS_KEY_FILE"))
    region_name = os.getenv(f"{prefix}_REGION", "auto").strip() or "auto"
    addressing_style = os.getenv(f"{prefix}_ADDRESSING_STYLE", "path").strip() or "path"
    s3_compatibility = os.getenv(f"{prefix}_S3_COMPATIBILITY", "aws").strip().lower() or "aws"
    if not all((endpoint, bucket, access, secret)):
        return None
    if addressing_style not in {"auto", "path", "virtual"}:
        return None
    if s3_compatibility not in {"aws", "oci"}:
        return None
    return {
        "endpoint": endpoint,
        "bucket": bucket,
        "access": access or "",
        "secret": secret or "",
        "region_name": region_name,
        "addressing_style": addressing_style,
        "s3_compatibility": s3_compatibility,
    }


def _s3_client(config: dict[str, str]):
    return create_s3_client(
        endpoint_url=config["endpoint"],
        access_key_id=config["access"],
        secret_access_key=config["secret"],
        region_name=config.get("region_name", "auto"),
        addressing_style=config.get("addressing_style", "path"),
        s3_compatibility=config.get("s3_compatibility", "aws"),
    )


def _upload_args(config: dict[str, str], metadata: dict[str, str], *, content_type: str | None = None) -> dict[str, Any]:
    args: dict[str, Any] = {"Metadata": metadata}
    if content_type:
        args["ContentType"] = content_type
    if config.get("s3_compatibility", "aws") == "aws":
        args["StorageClass"] = "STANDARD"
    return args


def _upload_and_verify(
    config: dict[str, str],
    ciphertext: Path,
    key: str,
    encrypted: EncryptedObject,
    readback: Path,
) -> dict[str, Any]:
    """Upload and read back exactly one already-encrypted Private-Database bundle."""
    if not ciphertext.is_file() or sha256_file(ciphertext) != encrypted.cipher_sha256:
        raise RuntimeError("本地备份密文缺失或哈希不一致")
    client = _s3_client(config)
    metadata = {
        "original-sha256": encrypted.original_sha256,
        "cipher-sha256": encrypted.cipher_sha256,
        "encryption": encrypted.algorithm,
    }
    client.upload_file(str(ciphertext), config["bucket"], key, ExtraArgs=_upload_args(config, metadata))
    head = client.head_object(Bucket=config["bucket"], Key=key)
    remote = head.get("Metadata") or {}
    if any(remote.get(name) != value for name, value in metadata.items()):
        raise RuntimeError("远端备份元数据校验失败")
    readback.parent.mkdir(parents=True, exist_ok=True)
    tmp = readback.with_name(f".{readback.name}.download")
    try:
        client.download_file(config["bucket"], key, str(tmp))
        if sha256_file(tmp) != encrypted.cipher_sha256:
            raise RuntimeError("远端备份回读哈希不一致")
    finally:
        tmp.unlink(missing_ok=True)
    return {
        "status": "verified",
        "object_key": key,
        "etag": str(head.get("ETag", "")).strip('"') or None,
        "original_sha256": encrypted.original_sha256,
        "cipher_sha256": encrypted.cipher_sha256,
        "encryption": encrypted.algorithm,
    }


def _upload_recovery_descriptor_and_verify(
    config: dict[str, str],
    descriptor: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    """Store only recovery metadata, never facts or plaintext, beside its cipher.

    A local manifest is useful for routine restore, but cannot survive a host
    loss.  The descriptor contains only hashes, object keys and receipt state;
    it lets a recovery node locate and verify the same encrypted bundle from
    either cold-backup store.
    """
    body = json_bytes(descriptor)
    digest = sha256_bytes(body)
    client = _s3_client(config)
    metadata = {"descriptor-sha256": digest, "kind": "social-archive-recovery-descriptor"}
    client.put_object(
        Bucket=config["bucket"],
        Key=key,
        Body=body,
        **_upload_args(config, metadata, content_type="application/json"),
    )
    head = client.head_object(Bucket=config["bucket"], Key=key)
    if (head.get("Metadata") or {}) != metadata:
        raise RuntimeError("远端恢复描述符元数据校验失败")
    response = client.get_object(Bucket=config["bucket"], Key=key)
    readback = response["Body"].read()
    if sha256_bytes(readback) != digest or readback != body:
        raise RuntimeError("远端恢复描述符回读哈希不一致")
    return {"status": "verified", "object_key": key, "sha256": digest}


def _create_tar(source: Path, out: Path) -> None:
    """Create a byte-stable gzip tar so unchanged facts remain content-addressed."""
    with out.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in sorted(source.rglob("*")):
                    if not path.is_file() or path.is_symlink():
                        continue
                    info = archive.gettarinfo(str(path), arcname=str(path.relative_to(source)))
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)


def _write_snapshot(facts: list[dict[str, Any]], root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    ordered = sorted(facts, key=lambda item: str(item["content"]["id"]))
    digests = [fact_sha256(item) for item in ordered]
    header = {
        "schema_version": "1.0",
        "kind": "social_archive.private_database_recovery_bundle",
        "fact_count": len(ordered),
        "fact_sha256s": digests,
        "facts_sha256": sha256_bytes(b"".join(bytes.fromhex(digest) for digest in digests)),
    }
    atomic_write(root / "snapshot.json", json.dumps(header, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n", mode=0o600)
    atomic_write(root / "facts.ndjson", b"".join(fact_bytes(item) for item in ordered), mode=0o600)
    archive = root.parent / "private-database-facts.tar.gz"
    _create_tar(root, archive)
    return archive


def _blocked(message: str, *, code: str = "BACKUP_PREREQUISITE_MISSING") -> int:
    print(json.dumps({
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "status": "BLOCKED_ENVIRONMENT",
        "error_code": code,
        "message": message,
        "local_checkout": False,
    }, ensure_ascii=False))
    return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an API-synchronized, age-encrypted Private-Database cold backup for R2 then OCI")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true", help="oneshot compatibility flag")
    parser.add_argument("--output")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.age_recipient:
        return _blocked("缺少 SOCIAL_ARCHIVE_AGE_RECIPIENT；禁止明文备份", code="AGE_RECIPIENT_MISSING")
    r2_config = _s3_config("r2")
    oci_config = _s3_config("oci")
    if not r2_config or not oci_config:
        return _blocked("R2 与 OCI 都必须已配置；禁止只写单份 Private-Database 冷备", code="COLD_BACKUP_STORE_UNCONFIGURED")
    if not args.dry_run and not shutil.which("age"):
        return _blocked("缺少 age 命令，不能生成远端密文", code="AGE_BINARY_MISSING")

    limit = min(max(args.limit, 1), 1000)
    if args.dry_run and not settings.runtime_db.is_file():
        return _blocked("Runtime Journal 尚未初始化；dry-run 不创建本地状态", code="RUNTIME_JOURNAL_UNAVAILABLE")

    settings.ensure_directories()
    store = RuntimeStore(settings.runtime_db)
    store.initialize()
    facts = delivered_completed_content_facts(store, limit=limit)
    if not facts:
        return _blocked("没有已由 Private-Database API 验证的当前完成态事实，拒绝生成空或未同步冷备", code="PRIVATE_DATABASE_SYNC_PREREQUISITE")
    if args.dry_run:
        print(json.dumps({
            "schema_version": "1.0",
            "generated_at": utcnow(),
            "status": "READY",
            "dry_run": True,
            "fact_count": len(facts),
            "source": "Private-Database API-synchronized canonical facts",
            "stores": ["r2", "oci"],
            "local_checkout": False,
        }, ensure_ascii=False))
        return 0

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup_root = Path(args.output).resolve() if args.output else settings.data_root / "backups/private-database" / stamp
    backup_root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="social-archive-private-backup-") as temp_dir:
            temporary_root = Path(temp_dir)
            plain = _write_snapshot(facts, temporary_root / "bundle")
            original_sha = sha256_file(plain)
            encryptor = AgeEncryptor(recipient=settings.age_recipient, root=backup_root / "encrypted")
            encrypted = encryptor.encrypt(StoredObject(original_sha, plain.stat().st_size, plain, "application/gzip"))
    except Exception as exc:  # noqa: BLE001 - encryption binary/recipient boundary
        print(json.dumps({
            "schema_version": "1.0",
            "generated_at": utcnow(),
            "status": "DEGRADED",
            "error_code": "COLD_BACKUP_ENCRYPTION_FAILED",
            "error_type": exc.__class__.__name__,
            "local_checkout": False,
        }, ensure_ascii=False))
        return 4

    if encrypted.cipher_byte_size >= settings.r2_hard_bytes or encrypted.cipher_byte_size >= settings.oci_hard_bytes:
        print(json.dumps({
            "schema_version": "1.0",
            "generated_at": utcnow(),
            "status": "DEGRADED",
            "error_code": "COLD_BACKUP_HARD_QUOTA",
            "cipher_byte_size": encrypted.cipher_byte_size,
            "local_checkout": False,
        }, ensure_ascii=False))
        return 4

    key = f"backups/private-database/{stamp}/{encrypted.original_sha256}.tar.gz.age"
    # Both stores receive the same locally produced ciphertext, so the offsite
    # copy does not depend on the primary having succeeded.  Chaining them meant
    # an R2 outage marked OCI blocked_prerequisite and never attempted it, taking
    # the offsite copy from two copies straight to zero -- exactly when it is
    # most needed.  Attempt each independently; the overall verdict below still
    # requires both to verify.
    receipts: dict[str, Any] = {}
    for store_id, store_config in (("r2", r2_config), ("oci", oci_config)):
        try:
            receipts[store_id] = _upload_and_verify(
                store_config, encrypted.path, key, encrypted, backup_root / "readback" / f"{store_id}.age"
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary
            receipts[store_id] = {"status": "failed", "error_code": exc.__class__.__name__}

    manifest = {
        "schema_version": "3.0",
        "created_at": utcnow(),
        "source": "Private-Database API-synchronized canonical facts",
        "fact_count": len(facts),
        "fact_sha256s": [fact_sha256(item) for item in sorted(facts, key=lambda item: str(item["content"]["id"]))],
        "ciphertext": str(encrypted.path),
        "original_sha256": encrypted.original_sha256,
        "original_byte_size": encrypted.original_byte_size,
        "cipher_sha256": encrypted.cipher_sha256,
        "cipher_byte_size": encrypted.cipher_byte_size,
        "encryption": encrypted.algorithm,
        "recipient_fingerprint": encryptor.recipient_fingerprint,
        "remote_key": key,
        "receipts": receipts,
        "local_checkout": False,
    }
    descriptor_key = f"backups/private-database/{stamp}/recovery.json"
    descriptor = {
        "schema_version": "1.0",
        "kind": "social_archive.private_database_recovery_descriptor",
        "created_at": manifest["created_at"],
        "remote_key": key,
        "original_sha256": encrypted.original_sha256,
        "cipher_sha256": encrypted.cipher_sha256,
        "encryption": encrypted.algorithm,
        "fact_count": len(facts),
        "receipts": receipts,
    }
    descriptor_receipts: dict[str, Any] = {}
    for store_id, config in (("r2", r2_config), ("oci", oci_config)):
        if receipts.get(store_id, {}).get("status") != "verified":
            descriptor_receipts[store_id] = {"status": "blocked_prerequisite", "error_code": "COLD_BACKUP_CIPHER_NOT_VERIFIED"}
            continue
        try:
            descriptor_receipts[store_id] = _upload_recovery_descriptor_and_verify(config, descriptor, descriptor_key)
        except Exception as exc:  # noqa: BLE001 - provider boundary
            descriptor_receipts[store_id] = {"status": "failed", "error_code": exc.__class__.__name__}
    manifest["recovery_descriptor"] = {
        "object_key": descriptor_key,
        "sha256": sha256_bytes(json_bytes(descriptor)),
        "receipts": descriptor_receipts,
    }
    manifest_path = backup_root / "manifest.json"
    atomic_write(manifest_path, (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"), mode=0o600)
    verified = all(receipts.get(store_id, {}).get("status") == "verified" for store_id in ("r2", "oci")) and all(
        descriptor_receipts.get(store_id, {}).get("status") == "verified" for store_id in ("r2", "oci")
    )
    status = "PASS" if verified else "DEGRADED"
    print(json.dumps({
        "status": status,
        "manifest": str(manifest_path),
        "fact_count": len(facts),
        "verified_remote_copies": 2 if verified else sum(receipt.get("status") == "verified" for receipt in receipts.values()),
        "verified_recovery_descriptors": sum(
            receipt.get("status") == "verified" for receipt in descriptor_receipts.values()
        ),
        "cipher_sha256": encrypted.cipher_sha256,
        "local_checkout": False,
    }, ensure_ascii=False))
    return 0 if verified else 4


if __name__ == "__main__":
    raise SystemExit(main())
