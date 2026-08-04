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
from github_release_backup import (  # noqa: E402  同上：Draft Release 那一套已经写好了
    github_cli_environment,
    run as run_gh,
    verify_draft_release,
    verify_private_repository,
)
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
    """确定性 gzip：**mtime 写 0，filename 写空**。

    默认的 gzip 会把当前时间写进头部，于是同样的输入每次压出来的字节都不同，
    `original_sha256` 就永远在变——那样「这次和上次一样吗」根本没法判。

    **只置 mtime=0 还不够。** GzipFile 拿到 fileobj 时会从 `fileobj.name`
    推出一个文件名也写进头部——实测：同样的内容写进 a.gz 与 b.gz，
    哈希分别是 7bddc5ee… 与 a5b42f87…，**不一致**；显式 `filename=""`
    之后两次都是 fc32ac2f…。这是我自己的自测抓出来的。

    另一半：VACUUM INTO 对未变化的库是确定性的（同一个库连做三次，
    哈希一致，且构造里带了 freelist）。两半都确定，整条链才可比。
    """
    with source.open("rb") as raw, target.open("wb") as out:
        with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=6, mtime=0, filename="") as packed:
            shutil.copyfileobj(raw, packed, length=1024 * 1024)
    return target


def previous_original_sha256(backups_root: Path) -> str | None:
    """上一次成功的快照明文哈希。找不到就返回 None（当作「变了」）。"""
    if not backups_root.is_dir():
        return None
    for directory in sorted(backups_root.iterdir(), reverse=True):
        manifest = directory / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if int(data.get("verified_remote_copies") or 0) >= REQUIRED_VERIFIED_COPIES:
            return str(data.get("original_sha256") or "") or None
    return None


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
    # **让它能跟着复制定时器跑。**
    #
    # 制品每 ~15 分钟复制一次，而索引原来一天才备一次。机器在这两者之间没了，
    # 就会留下一批**有制品、没索引行**的孤儿密文——救回来也不知道是什么。
    # 加上这个开关之后，可以每 15 分钟跑一次而只在库真的变了时才上传：
    # 闲着的那些轮次是一次 VACUUM INTO + 一次哈希，不产生任何流量。
    parser.add_argument("--skip-if-unchanged", action="store_true")
    # 制品有三份副本，索引原来只有两份（R2 + OCI）。**同一件事该有同一个标准。**
    parser.add_argument("--github", action="store_true",
                        help="额外把快照放进 GitHub 私有仓的 Draft Release，凑齐第三份")
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

    # **先不建目录。** 这一轮可能因为「库没变」而什么都不产出；
    # 先建再删会让「脚本里不许有删除动作」这条判据失去意义——
    # 而那条判据守的是「不许自动删历史备份」，是对的。
    #
    # 密文先落在临时目录里；确认这一轮要上传之后，再建正式目录并把它挪过去。
    # （**别让 encrypted.path 指向一个 with 块退出就消失的地方**——
    #  第一版就是这么写的，上传会拿到一个不存在的文件。）
    with tempfile.TemporaryDirectory(prefix="social-archive-db-backup-") as temporary:
        work = Path(temporary)
        try:
            snapshot = snapshot_database(settings.runtime_db, work / "runtime.sqlite3")
            packed = _gzip(snapshot, work / "runtime.sqlite3.gz")
            original_sha = sha256_file(packed)
            encryptor = AgeEncryptor(recipient=settings.age_recipient, root=work / "encrypted")
            encrypted = encryptor.encrypt(
                StoredObject(original_sha, packed.stat().st_size, packed, "application/gzip")
            )
            snapshot_bytes = snapshot.stat().st_size
        except Exception as exc:  # noqa: BLE001 - 快照/加密边界
            return _fail("RUNTIME_DB_SNAPSHOT_FAILED", "运行库快照或加密失败",
                         error_type=exc.__class__.__name__)

        if args.skip_if_unchanged:
            previous = previous_original_sha256(settings.data_root / "backups/runtime-db")
            if previous and previous == encrypted.original_sha256:
                print(json.dumps({
                    "schema_version": "1.0", "generated_at": utcnow(), "status": "PASS",
                    "skipped": True, "reason": "RUNTIME_DB_UNCHANGED",
                    "original_sha256": encrypted.original_sha256,
                }, ensure_ascii=False))
                return 0

        # 这一轮确实要上传了，正式目录现在才建。
        ciphertext = root / "encrypted" / encrypted.path.name
        ciphertext.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(encrypted.path, ciphertext)

    key = f"backups/runtime-db/{stamp}/{encrypted.original_sha256}.sqlite3.gz.age"
    receipts: dict[str, Any] = {}
    try:
        receipts["r2"] = _upload_and_verify(r2_config, ciphertext, key, encrypted,
                                            root / "readback" / "r2.age")
    except Exception as exc:  # noqa: BLE001 - 提供方边界
        receipts["r2"] = {"status": "failed", "error_code": exc.__class__.__name__}
        # **第一份没验成就不往下走**：免得两边都是坏的还各自报成功。
        receipts["oci"] = {"status": "blocked_prerequisite", "error_code": "R2_BACKUP_NOT_VERIFIED"}
    else:
        try:
            receipts["oci"] = _upload_and_verify(oci_config, ciphertext, key, encrypted,
                                                 root / "readback" / "oci.age")
        except Exception as exc:  # noqa: BLE001 - 提供方边界
            receipts["oci"] = {"status": "failed", "error_code": exc.__class__.__name__}

    # **第三份：GitHub 私有仓的 Draft Release。**
    #
    # 制品有三份副本，索引原来只有两份。同一件事该有同一个标准——尤其索引
    # 比制品更要紧：制品丢一个是丢一条内容，索引丢了是 552 个都说不出是什么。
    #
    # 复用 github_release_backup.py 里那一套（建 Draft、确认它真是 Draft、
    # 上传、下载回读比哈希），不抄第二遍。
    if args.github and receipts.get("r2", {}).get("status") == "verified":
        repository = str(getattr(settings, "github_archive_repository", "") or "").strip()
        github_env = github_cli_environment(settings.github_token_file)
        if not repository or github_env is None:
            receipts["github"] = {"status": "blocked_prerequisite",
                                  "error_code": "GITHUB_VAULT_NOT_CONFIGURED"}
        elif not shutil.which("gh"):
            receipts["github"] = {"status": "blocked_prerequisite", "error_code": "GH_BINARY_MISSING"}
        else:
            tag = f"social-archive-runtime-db-{stamp}"
            try:
                verify_private_repository(repository, env=github_env)
                run_gh(["gh", "release", "create", tag, "--repo", repository, "--draft",
                        "--title", tag, "--notes", "Social Archive runtime index snapshot (age-encrypted)"],
                       env=github_env)
                verify_draft_release(repository, tag, env=github_env)
                run_gh(["gh", "release", "upload", tag, str(ciphertext), "--repo", repository],
                       env=github_env)
                with tempfile.TemporaryDirectory(prefix="social-archive-gh-db-readback-") as readback:
                    download_dir = Path(readback)
                    run_gh(["gh", "release", "download", tag, "--repo", repository,
                            "--dir", str(download_dir)], env=github_env)
                    fetched = download_dir / ciphertext.name
                    if not fetched.is_file() or sha256_file(fetched) != encrypted.cipher_sha256:
                        raise RuntimeError("GitHub Draft Release 回读哈希不一致")
                receipts["github"] = {
                    "status": "verified",
                    "object_key": f"gh-release://{repository}/{tag}#{ciphertext.name}",
                    "cipher_sha256": encrypted.cipher_sha256,
                    "original_sha256": encrypted.original_sha256,
                    "encryption": encrypted.algorithm,
                }
            except Exception as exc:  # noqa: BLE001 - 提供方边界
                receipts["github"] = {"status": "failed", "error_code": exc.__class__.__name__}

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
        "required_verified_copies": REQUIRED_VERIFIED_COPIES,
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
