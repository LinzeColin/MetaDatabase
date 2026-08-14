from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.encryption import AgeEncryptor
from social_archive.storage import S3ReplicaStore, StoredObject
from social_archive.utils import read_secret, utcnow


def _store_config(store_id: str) -> tuple[dict[str, str] | None, str | None]:
    prefix = f"SOCIAL_ARCHIVE_{store_id.upper()}"
    endpoint = os.getenv(f"{prefix}_ENDPOINT", "").strip()
    bucket = os.getenv(f"{prefix}_BUCKET", "").strip()
    access = read_secret(os.getenv(f"{prefix}_ACCESS_KEY_ID_FILE"))
    secret = read_secret(os.getenv(f"{prefix}_SECRET_ACCESS_KEY_FILE"))
    region_name = os.getenv(f"{prefix}_REGION", "auto").strip() or "auto"
    addressing_style = os.getenv(f"{prefix}_ADDRESSING_STYLE", "path").strip() or "path"
    s3_compatibility = os.getenv(f"{prefix}_S3_COMPATIBILITY", "aws").strip().lower() or "aws"
    if not all((endpoint, bucket, access, secret)):
        return None, f"{store_id.upper()} 的 endpoint、bucket 或秘密文件未配置"
    if addressing_style not in {"auto", "path", "virtual"}:
        return None, f"{store_id.upper()} 的 addressing style 非法"
    if s3_compatibility not in {"aws", "oci"}:
        return None, f"{store_id.upper()} 的 S3 compatibility 非法"
    return {
        "store_id": store_id,
        "endpoint_url": endpoint,
        "bucket": bucket,
        "access_key_id": access or "",
        "secret_access_key": secret or "",
        "prefix": "primary-objects",
        "region_name": region_name,
        "addressing_style": addressing_style,
        "s3_compatibility": s3_compatibility,
    }, None


def _required_r2_receipt_error(store: RuntimeStore, artifact_id: str, encrypted: Any) -> str | None:
    """Return a fail-closed reason unless OCI can reuse the verified R2 cipher."""
    receipt = store.get_object_replica(artifact_id, "r2")
    if not receipt:
        return "R2_REPLICA_MISSING"
    if receipt.get("status") != "verified":
        return "R2_REPLICA_NOT_VERIFIED"
    if receipt.get("original_sha256") != encrypted.original_sha256:
        return "R2_ORIGINAL_SHA_MISMATCH"
    if receipt.get("encryption") != encrypted.algorithm:
        return "R2_ENCRYPTION_MISMATCH"
    if receipt.get("verified_sha256") != encrypted.cipher_sha256:
        return "R2_CIPHER_SHA_MISMATCH"
    return None


def _replicate_one(
    store: RuntimeStore,
    remote: S3ReplicaStore,
    encryptor: AgeEncryptor,
    row: dict[str, Any],
    *,
    readback_root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    source = Path(str(row.get("local_path") or ""))
    if not source.is_file() or source.is_symlink():
        store.upsert_object_replica(
            artifact_id=row["id"], store_id=remote.store_id, object_key="unavailable",
            status="failed", last_error_code="LOCAL_OBJECT_MISSING",
        )
        return {"artifact_id": row["id"], "status": "FAILED", "error_code": "LOCAL_OBJECT_MISSING"}
    obj = StoredObject(
        sha256=str(row["sha256"]), byte_size=int(row["byte_size"]), path=source,
        media_type=row.get("media_type"),
    )
    try:
        encrypted = encryptor.encrypt(obj)
    except Exception as exc:  # noqa: BLE001 - boundary converts to bounded evidence
        store.upsert_object_replica(
            artifact_id=row["id"], store_id=remote.store_id, object_key="encryption-failed",
            status="failed", last_error_code=exc.__class__.__name__,
        )
        return {"artifact_id": row["id"], "status": "FAILED", "error_code": exc.__class__.__name__}
    object_key = remote.object_key(encrypted.original_sha256)
    if remote.store_id == "oci":
        prerequisite_error = _required_r2_receipt_error(store, row["id"], encrypted)
        if prerequisite_error:
            store.upsert_object_replica(
                artifact_id=row["id"], store_id=remote.store_id, object_key=object_key,
                status="failed", verified_sha256=encrypted.cipher_sha256,
                original_sha256=encrypted.original_sha256, encryption=encrypted.algorithm,
                last_error_code=prerequisite_error,
            )
            return {"artifact_id": row["id"], "status": "FAILED", "error_code": prerequisite_error}
    if dry_run:
        return {
            "artifact_id": row["id"], "status": "READY", "object_key": object_key,
            "original_sha256": encrypted.original_sha256, "cipher_sha256": encrypted.cipher_sha256,
        }
    try:
        key, etag = remote.put_encrypted(encrypted)
        readback = readback_root / remote.store_id / f"{encrypted.original_sha256}.age"
        remote.download_verified(key, readback, encrypted.cipher_sha256)
        readback.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 - S3 provider boundary
        store.upsert_object_replica(
            artifact_id=row["id"], store_id=remote.store_id, object_key=object_key,
            status="failed", original_sha256=encrypted.original_sha256,
            verified_sha256=encrypted.cipher_sha256, encryption=encrypted.algorithm,
            last_error_code=exc.__class__.__name__,
        )
        return {"artifact_id": row["id"], "status": "FAILED", "error_code": exc.__class__.__name__}
    store.upsert_object_replica(
        artifact_id=row["id"], store_id=remote.store_id, object_key=key,
        status="verified", etag=etag, verified_sha256=encrypted.cipher_sha256,
        original_sha256=encrypted.original_sha256, encryption=encrypted.algorithm,
    )
    return {
        "artifact_id": row["id"], "status": "PASS", "object_key": key,
        "original_sha256": encrypted.original_sha256, "cipher_sha256": encrypted.cipher_sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", choices=["r2", "oci", "all"], default="all")
    parser.add_argument("--limit", type=int, default=100)
    # The CLI always performs one bounded pass.  Keep the Task Pack's explicit
    # spelling without changing the existing systemd invocation.
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    if not settings.age_recipient:
        report = {"schema_version": "1.0", "generated_at": utcnow(), "status": "BLOCKED_ENVIRONMENT", "message": "缺少 SOCIAL_ARCHIVE_AGE_RECIPIENT；禁止明文复制"}
        print(json.dumps(report, ensure_ascii=False))
        return 3
    settings.ensure_directories()
    runtime = RuntimeStore(settings.runtime_db)
    runtime.initialize()
    encryptor = AgeEncryptor(recipient=settings.age_recipient, root=settings.staging_root / "encrypted")
    selected = ["r2", "oci"] if args.store == "all" else [args.store]
    measured = runtime.artifact_unique_bytes()
    limits = {"r2": settings.r2_hard_bytes, "oci": settings.oci_hard_bytes}
    report: dict[str, Any] = {"schema_version": "1.0", "generated_at": utcnow(), "dry_run": args.dry_run, "once": args.once, "encryption": "age-x25519", "stores": {}}
    attempted = failures = blocked = 0
    for store_id in selected:
        runtime.set_quota_state(store_id, measured, int(limits[store_id] * 0.9), limits[store_id], "pause_l3" if measured >= limits[store_id] else "allow")
        if measured >= limits[store_id]:
            report["stores"][store_id] = {"status": "PAUSED_QUOTA", "measured_bytes": measured, "hard_bytes": limits[store_id]}
            blocked += 1
            continue
        config, error = _store_config(store_id)
        if error or not config:
            report["stores"][store_id] = {"status": "BLOCKED_ENVIRONMENT", "message": error}
            blocked += 1
            continue
        remote = S3ReplicaStore(**config)
        rows = runtime.list_artifacts_for_replication(
            store_id,
            limit=max(1, min(args.limit, 1000)),
            requires_verified_store="r2" if store_id == "oci" else None,
        )
        results = [
            _replicate_one(runtime, remote, encryptor, row, readback_root=settings.staging_root / "readback", dry_run=args.dry_run)
            for row in rows
        ]
        attempted += len(results)
        failures += sum(item["status"] == "FAILED" for item in results)
        report["stores"][store_id] = {
            "status": "PASS" if not any(item["status"] == "FAILED" for item in results) else "DEGRADED",
            "attempted": len(results), "results": results,
        }
    report["completion"] = runtime.replication_completion()
    # **索引也要出现在这份状态里。**
    #
    # 这份 JSON 是对外的耐久性信号。2026-08-04 之前它写着
    # `all_three_verified: 549 / pending: 0 / PASS`——**每个字都是真的**，
    # 而当时运行库索引全世界只有一份：552 个加密块躺在三个云上，
    # 没有任何东西说得出它们分别是什么。
    #
    # 「制品都齐了」被当成了「档案馆安全了」。差别不在数字对不对，
    # 在于**没显示的那一格**。
    report["index_backup"] = _index_backup_status(settings)
    report["status"] = "PASS" if failures == 0 and blocked == 0 else ("DEGRADED" if attempted else "BLOCKED_ENVIRONMENT")
    output = settings.data_root / "status/object-replication.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else (4 if attempted else 3)


def _index_backup_status(settings) -> dict[str, Any]:
    """运行库快照最近一次备成什么样。

    只读 backup_runtime_db.py 落下的 manifest，不重新计算、不联网——
    这份报告是复制任务顺手带出来的，不该在这里再跑一遍备份。
    """
    root = settings.data_root / "backups/runtime-db"
    if not root.is_dir():
        return {"status": "MISSING", "message": "运行库索引从未备份过——制品救得回来，而没有东西说得出它们是什么"}
    for directory in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True):
        manifest = directory / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        verified = int(data.get("verified_remote_copies") or 0)
        return {
            "status": "PASS" if verified >= 2 else "DEGRADED",
            "created_at": data.get("created_at"),
            "verified_remote_copies": verified,
            "stores": {name: receipt.get("status") for name, receipt in (data.get("receipts") or {}).items()},
            "snapshot_byte_size": data.get("snapshot_byte_size"),
        }
    return {"status": "MISSING", "message": "backups/runtime-db 下没有可用的 manifest"}


if __name__ == "__main__":
    raise SystemExit(main())
