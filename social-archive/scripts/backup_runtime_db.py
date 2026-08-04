#!/usr/bin/env python3
"""把运行库本身也备份走（v0.0.0.7 / INV-REVERSIBLE）。

## 为什么必须有它

2026-08-04 实测生产：

    制品（内容字节）   552 个，每个三份已验证副本（R2 + OCI + GitHub）
    运行库 sqlite3     **4.59 MB，全世界只有一份**——就在那块盘上

对象仓里只有 `primary-objects/sha256/…`（制品字节）和 GitHub 的 release 包
（也是制品字节）。`social-archive-backup.service` 备份的是「私有库事实」，
最近一次 `fact_count: 1`、1217 字节——**不是这个库**。

那块盘没了会怎样：三个云上躺着 552 个加密块，**而没有任何东西说得出
它们分别是什么**。标题、链接、关系、收藏时间、artifact→content 的对应、
导出回执——全在这个 sqlite 里。制品还在，档案馆没了。

T16 的标题一直是「549/549 制品三副本齐全」。那句话是真的，
而它从没提过：**给这些制品赋予意义的那张索引，只有一份。**

## 做法

1. `VACUUM INTO` 出一个一致快照。**不是 cp**：库是 WAL 模式，
   直接拷文件会拿到一个撕裂的中间态（还漏掉 -wal 里未合并的事务）。
   VACUUM INTO 由 SQLite 自己保证一致性，且不需要停服。
2. gzip → age 加密（与制品同一个 recipient）。
3. 传 R2，回读比对哈希；成功了再传 OCI，同样回读比对。
   顺序是刻意的：**第一份没验成就不往下走**，免得两边都是坏的。
4. 写 manifest（明文哈希、密文哈希、字节数、两份回执）。
5. 少于两份已验证副本 → 退出码非零。**「传上去了」不算数，「读回来一致」才算。**

## 边界

· 快照落在 data_root/backups/runtime-db/<时间戳>/ 下，与制品的 CAS 分开。
· 密钥仍然只从 0600 Secret 读，值不进日志、不进 manifest。
· **不删旧快照。** 保留策略是运维决定，这里只管产出；
  自动删除历史备份是那种「出事才发现」的操作，不该由脚本自作主张。
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backup import _s3_config, _upload_and_verify  # noqa: E402  复用同一份实现，不抄第二遍
from social_archive.config import Settings  # noqa: E402
from social_archive.encryption import AgeEncryptor  # noqa: E402
from social_archive.storage import StoredObject  # noqa: E402
from social_archive.utils import sha256_file, utcnow  # noqa: E402

REQUIRED_VERIFIED_COPIES = 2


def snapshot_database(runtime_db: Path, target: Path) -> Path:
    """用 VACUUM INTO 取一致快照。

    **不能用 cp。** 库跑在 WAL 模式下，直接拷文件会拿到撕裂的中间态，
    而且 -wal 里尚未合并的事务不在那个文件里。
    """
    if not runtime_db.is_file():
        raise FileNotFoundError(f"运行库不存在：{runtime_db}")
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"file:{runtime_db}?mode=ro", uri=True)
    try:
        connection.execute("VACUUM INTO ?", (str(target),))
    finally:
        connection.close()
    return target


def _gzip(source: Path, target: Path) -> Path:
    with source.open("rb") as raw, gzip.open(target, "wb", compresslevel=6) as packed:
        shutil.copyfileobj(raw, packed, length=1024 * 1024)
    return target


def _fail(code: str, message: str, **extra: Any) -> int:
    print(json.dumps({
        "schema_version": "1.0", "generated_at": utcnow(), "status": "FAIL",
        "error_code": code, "message": message, **extra,
    }, ensure_ascii=False))
    return 4


def main() -> int:
    parser = argparse.ArgumentParser(description="把运行库快照加密后复制到 R2 与 OCI")
    parser.add_argument("--output")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.age_recipient:
        return _fail("AGE_RECIPIENT_MISSING", "缺少 age 公钥，无法加密运行库快照")
    if not settings.runtime_db.is_file():
        return _fail("RUNTIME_DB_MISSING", f"运行库不存在：{settings.runtime_db}")

    r2_config = _s3_config("r2")
    oci_config = _s3_config("oci")
    if not r2_config or not oci_config:
        missing = [name for name, config in (("r2", r2_config), ("oci", oci_config)) if not config]
        return _fail("OBJECT_STORE_NOT_CONFIGURED", f"对象仓未配置：{missing}")

    stamp = utcnow().replace("-", "").replace(":", "").replace(".", "")[:15] + "Z"
    root = Path(args.output).resolve() if args.output else settings.data_root / "backups/runtime-db" / stamp

    if args.dry_run:
        print(json.dumps({
            "schema_version": "1.0", "generated_at": utcnow(), "status": "PASS",
            "dry_run": True, "runtime_db": str(settings.runtime_db),
            "runtime_db_bytes": settings.runtime_db.stat().st_size,
            "would_write_to": str(root),
        }, ensure_ascii=False))
        return 0

    root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="social-archive-db-backup-") as temporary:
            work = Path(temporary)
            snapshot = snapshot_database(settings.runtime_db, work / "runtime.sqlite3")
            packed = _gzip(snapshot, work / "runtime.sqlite3.gz")
            original_sha = sha256_file(packed)
            encryptor = AgeEncryptor(recipient=settings.age_recipient, root=root / "encrypted")
            encrypted = encryptor.encrypt(
                StoredObject(original_sha, packed.stat().st_size, packed, "application/gzip")
            )
            snapshot_bytes = snapshot.stat().st_size
    except Exception as exc:  # noqa: BLE001 - 快照/加密边界
        return _fail("RUNTIME_DB_SNAPSHOT_FAILED", "运行库快照或加密失败",
                     error_type=exc.__class__.__name__)

    key = f"backups/runtime-db/{stamp}/{encrypted.original_sha256}.sqlite3.gz.age"
    receipts: dict[str, Any] = {}
    try:
        receipts["r2"] = _upload_and_verify(r2_config, encrypted.path, key, encrypted,
                                            root / "readback" / "r2.age")
    except Exception as exc:  # noqa: BLE001 - 提供方边界
        receipts["r2"] = {"status": "failed", "error_code": exc.__class__.__name__}
        # **第一份没验成就不往下走**：免得两边都是坏的还各自报成功。
        receipts["oci"] = {"status": "blocked_prerequisite", "error_code": "R2_BACKUP_NOT_VERIFIED"}
    else:
        try:
            receipts["oci"] = _upload_and_verify(oci_config, encrypted.path, key, encrypted,
                                                 root / "readback" / "oci.age")
        except Exception as exc:  # noqa: BLE001 - 提供方边界
            receipts["oci"] = {"status": "failed", "error_code": exc.__class__.__name__}

    verified = sum(1 for receipt in receipts.values() if receipt.get("status") == "verified")
    manifest = {
        "schema_version": "1.0",
        "kind": "social_archive.runtime_db_snapshot",
        "created_at": utcnow(),
        "encryption": "age-x25519",
        "snapshot_byte_size": snapshot_bytes,
        "original_sha256": encrypted.original_sha256,
        "cipher_sha256": encrypted.cipher_sha256,
        "cipher_byte_size": encrypted.cipher_byte_size,
        "object_key": key,
        "receipts": receipts,
        "verified_remote_copies": verified,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest["manifest"] = str(root / "manifest.json")
    # **「传上去了」不算数，「读回来一致」才算。**
    manifest["status"] = "PASS" if verified >= REQUIRED_VERIFIED_COPIES else "FAIL"
    print(json.dumps(manifest, ensure_ascii=False))
    return 0 if verified >= REQUIRED_VERIFIED_COPIES else 4


if __name__ == "__main__":
    sys.exit(main())
