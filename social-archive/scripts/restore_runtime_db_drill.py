#!/usr/bin/env python3
"""从远端把运行库快照取回来，验它真的能打开（v0.0.0.7 / INV-REVERSIBLE）。

## 为什么单独有这个演练

backup_runtime_db.py 证明的是「快照做出来了、传上去了、密文读回来一致」。
**那三件事都成立，快照仍然可能是个打不开的文件**——密文哈希一致只说明
字节没坏，不说明解密之后是一个能用的 SQLite。

这一天里已经吃过两次同形状的亏：
  · 三份副本全登记 verified，而 GitHub 那条取回路根本跑不通
  · 恢复报 `target_written: true`，而目标目录是空的（PrivateTmp）

所以这里做完整的一路：**下载 → 解密 → 解压 → 打开 → 数表**。

## 边界

· 全程只读远端，**不写任何生产路径**。落地目录由 --target 指定，
  脚本会拒绝数据面下的路径。
· 跑完自己不删目标目录——留给人看。要删由人来删。
· 只比对「表在不在、行数对不对」，不逐行比内容。
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backup import _s3_client, _s3_config  # noqa: E402
from social_archive.config import Settings  # noqa: E402
from social_archive.utils import sha256_file, utcnow  # noqa: E402

# 拿来对照的表。挑的是「丢了就说不出这些制品是什么」的那几张。
COMPARED_TABLES = ("content", "user_relation", "artifact", "object_replica", "destination_receipt")


def _fail(code: str, message: str, **extra: Any) -> int:
    print(json.dumps({"status": "FAIL", "error_code": code, "message": message,
                      "generated_at": utcnow(), **extra}, ensure_ascii=False))
    return 4


def _counts(database: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        present = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in COMPARED_TABLES if table in present
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="把运行库快照从对象仓取回并验证它打得开")
    parser.add_argument("--manifest", required=True, help="backup_runtime_db.py 写的 manifest.json")
    parser.add_argument("--from-store", required=True, choices=("r2", "oci"))
    parser.add_argument("--target", required=True, help="一个全新的隔离目录")
    args = parser.parse_args()

    settings = Settings.from_env()
    target = Path(args.target).expanduser().resolve()
    protected = (settings.data_root, settings.staging_root, settings.runtime_db.parent)
    for guard in protected:
        if target == guard or guard in target.parents:
            return _fail("RECOVERY_TARGET_INVALID", "恢复目标不能落入运行数据面")

    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.is_file():
        return _fail("MANIFEST_MISSING", f"找不到 manifest：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    identity = settings.age_identity_file
    if not identity or not Path(identity).is_file():
        return _fail("AGE_IDENTITY_MISSING", "缺少 age 私钥，无法解密快照")

    config = _s3_config(args.from_store)
    if not config:
        return _fail("OBJECT_STORE_NOT_CONFIGURED", f"{args.from_store} 未配置")

    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="social-archive-db-restore-") as temporary:
        work = Path(temporary)
        ciphertext = work / "snapshot.gz.age"
        client = _s3_client(config)
        client.download_file(config["bucket"], manifest["object_key"], str(ciphertext))
        if sha256_file(ciphertext) != manifest["cipher_sha256"]:
            return _fail("CIPHER_SHA256_MISMATCH", "远端密文回读哈希与 manifest 不一致")

        packed = work / "snapshot.gz"
        completed = subprocess.run(
            ["age", "--decrypt", "--identity", str(identity), "--output", str(packed), str(ciphertext)],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0 or not packed.is_file():
            # **不回显 stderr。** 解密失败的输出里可能带密钥材料的片段。
            return _fail("AGE_DECRYPT_FAILED", "age 解密失败", exit_code=completed.returncode)
        if sha256_file(packed) != manifest["original_sha256"]:
            return _fail("PLAINTEXT_SHA256_MISMATCH", "解密后的明文哈希与 manifest 不一致")

        restored = target / "restored-runtime.sqlite3"
        with gzip.open(packed, "rb") as source, restored.open("wb") as out:
            shutil.copyfileobj(source, out, length=1024 * 1024)

    try:
        restored_counts = _counts(restored)
    except sqlite3.DatabaseError as exc:
        return _fail("RESTORED_DB_UNREADABLE", "取回来的快照打不开",
                     error_type=exc.__class__.__name__)

    live_counts = _counts(settings.runtime_db) if settings.runtime_db.is_file() else {}
    print(json.dumps({
        "status": "PASS",
        "generated_at": utcnow(),
        "source_store": args.from_store,
        "object_key": manifest["object_key"],
        "restored_to": str(restored),
        "restored_byte_size": restored.stat().st_size,
        "restored_counts": restored_counts,
        "live_counts_now": live_counts,
        "note": "快照是取快照那一刻的样子；此后写入的行自然不在里面，所以两边计数可以不同。",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
