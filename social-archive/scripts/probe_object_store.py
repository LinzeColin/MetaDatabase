from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path

from social_archive.encryption import AgeEncryptor
from social_archive.storage import ContentAddressedStore, S3ReplicaStore
from social_archive.utils import read_secret, utcnow


def config(name: str) -> dict[str, str | None]:
    prefix = "SOCIAL_ARCHIVE_R2_" if name == "r2" else "SOCIAL_ARCHIVE_OCI_"
    return {
        "endpoint": os.getenv(prefix + "ENDPOINT"),
        "bucket": os.getenv(prefix + "BUCKET"),
        "key": read_secret(os.getenv(prefix + "ACCESS_KEY_ID_FILE")),
        "secret": read_secret(os.getenv(prefix + "SECRET_ACCESS_KEY_FILE")),
        "region_name": os.getenv(prefix + "REGION", "auto").strip() or "auto",
        "addressing_style": os.getenv(prefix + "ADDRESSING_STYLE", "path").strip() or "path",
        "s3_compatibility": os.getenv(prefix + "S3_COMPATIBILITY", "aws").strip().lower() or "aws",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    # Keep the original positional spelling for existing operator notes, while
    # accepting the frozen Task Pack spelling.  A remote write/delete probe must
    # be an explicit action, never a side effect of a bare store argument.
    parser.add_argument("store_positional", nargs="?", choices=["r2", "oci", "all"])
    parser.add_argument("--store", choices=["r2", "oci", "all"])
    parser.add_argument("--encrypted-canary", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.store and args.store_positional and args.store != args.store_positional:
        parser.error("位置 store 与 --store 不一致")
    store_name = args.store or args.store_positional
    if not store_name:
        parser.error("必须指定 --store r2|oci|all")
    if not args.encrypted_canary and not args.dry_run:
        print(json.dumps({
            "status": "BLOCKED_USER_CONFIRMATION",
            "message": "对象探针会写入并回读 age 密文；请显式传入 --encrypted-canary，或使用 --dry-run。",
        }, ensure_ascii=False))
        return 3
    names = ["r2", "oci"] if store_name == "all" else [store_name]
    recipient = os.getenv("SOCIAL_ARCHIVE_AGE_RECIPIENT", "").strip()
    if not recipient:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "缺少 age recipient；禁止明文探针"}, ensure_ascii=False))
        return 3
    results = []
    with tempfile.TemporaryDirectory(prefix="social-archive-object-probe-") as tmp:
        root = Path(tmp)
        obj = ContentAddressedStore(root / "cas").put_bytes(
            f"social-archive-probe:{uuid.uuid4()}".encode(), suffix=".txt", media_type="text/plain"
        )
        encrypted = AgeEncryptor(recipient=recipient, root=root / "encrypted").encrypt(obj)
        for name in names:
            values = config(name)
            if not all(values.values()):
                results.append({"store": name, "status": "BLOCKED_ENVIRONMENT", "missing": [key for key, value in values.items() if not value]})
                continue
            if args.dry_run:
                results.append({"store": name, "status": "READY", "bucket": values["bucket"], "encryption": encrypted.algorithm})
                continue
            key = ""
            try:
                store = S3ReplicaStore(
                    store_id=name, endpoint_url=str(values["endpoint"]), bucket=str(values["bucket"]),
                    access_key_id=str(values["key"]), secret_access_key=str(values["secret"]), prefix="probes/social-archive",
                    region_name=str(values["region_name"]), addressing_style=str(values["addressing_style"]),
                    s3_compatibility=str(values["s3_compatibility"]),
                )
                key, etag = store.put_encrypted(encrypted)
                readback = root / f"{name}-readback.age"
                store.download_verified(key, readback, encrypted.cipher_sha256)
                store.client.delete_object(Bucket=store.bucket, Key=key)
                results.append({
                    "store": name, "status": "PASS", "key": key, "etag": etag,
                    "original_sha256": encrypted.original_sha256, "cipher_sha256": encrypted.cipher_sha256,
                    "deleted_after_probe": True,
                })
            except Exception as exc:  # noqa: BLE001 - external provider boundary
                results.append({"store": name, "status": "FAIL", "error_type": exc.__class__.__name__, "message": str(exc)[:500], "key": key or None})
    status = "FAIL" if any(item["status"] == "FAIL" for item in results) else (
        "BLOCKED_ENVIRONMENT" if any(item["status"] == "BLOCKED_ENVIRONMENT" for item in results) else (
            "READY" if args.dry_run else "PASS"
        )
    )
    document = {"schema_version": "2.0", "generated_at": utcnow(), "status": status, "results": results}
    Path("runtime/evidence").mkdir(parents=True, exist_ok=True)
    Path("runtime/evidence/object-store-probe.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document, ensure_ascii=False))
    return 0 if status in {"PASS", "READY"} else (3 if status == "BLOCKED_ENVIRONMENT" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
