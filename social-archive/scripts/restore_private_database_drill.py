#!/usr/bin/env python3
"""从远端把 Private-Database 的 fact 包取回来，逐条核哈希（v0.0.0.7 / INV-REVERSIBLE）。

## 为什么补这一个

2026-08-05 把「备份 timer 自主触发过一次」这件事验完之后，我在证据里写下
一句自认的缺口：

    不证明 private-database 那条链——这次只把 runtime-db 快照取回来了，
    那 100 条 fact 的副本仍然只有它自己的回执作证。

去看了一眼，缺口比想的更实在：`scripts/` 下只有 `sync_private_database.py`
（**写**的那一半），**没有任何东西把它写出去的东西读回来**。
这正是这个项目最常见的失败形态——建好了没接上，写进去了没人取出来。

runtime-db 那条链早就有 `restore_runtime_db_drill.py`；这一条一直没有。

## 它做完整的一路

    下载 → 核密文哈希 → age 解密 → 核明文哈希 → 解 tar → **逐条核 fact 哈希**

最后一步是这个演练与 runtime-db 那个的区别所在。密文哈希一致只说明字节没坏；
明文哈希一致只说明整包没坏。**而 manifest 里给了 100 条 fact 各自的 sha256**，
不逐条核一遍，就等于守着一张对得上的清单却从没点过数。

## 边界

· 全程只读远端，**不写任何生产路径**。落地目录由 --target 指定，
  数据面下的路径会被拒绝（沿用 runtime-db 演练那几条护栏）。
· 只核哈希与条数，不解释 fact 的内容对不对——那是另一件事。
· 跑完不自己删目标目录，留给人看。

## 用法

    sudo systemd-run --wait --collect --pipe --property=Type=exec \\
      --property=LoadCredential=r2_access_key_id:/opt/social-archive/runtime/secrets/r2_access_key_id \\
      ... /bin/bash -c '... python scripts/restore_private_database_drill.py \\
          --manifest <manifest.json> --from-store r2 --target <全新隔离目录>'

  （要 root 才读得到 age 私钥：备份只用公钥，恢复才要私钥。）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backup import _s3_client, _s3_config  # noqa: E402
from social_archive.config import Settings  # noqa: E402
from social_archive.utils import sha256_file, utcnow  # noqa: E402


def _fail(code: str, message: str, **extra: Any) -> int:
    print(json.dumps({"status": "FAIL", "error_code": code, "message": message,
                      "generated_at": utcnow(), **extra}, ensure_ascii=False))
    return 4


FACTS_FILE = "facts.ndjson"


def _hash_variants(root: Path) -> dict[str, list[str]]:
    """把 `facts.ndjson` 的**每一行**算 sha256，两种行尾口径各算一份。

    第一版按「一个 fact 一个文件」写，跑出来 restored_count=2 而不是 100，
    差点被我当成「远端那份少了 98 条」报出去。**去看了一眼包里到底是什么**：

        facts.ndjson   —— 100 条，一行一个 JSON
        snapshot.json  —— 清单副本

    包一点问题都没有，是**我对它的结构猜错了**。指错原因比不报更糟：
    这一条要是发出去，下一个人会去查一个根本没坏的备份链。

    行尾算不算进哈希，同样不猜：两种都算，看哪一种和 manifest 对得上，
    并把用的是哪一种如实报出来。
    """
    facts = root / FACTS_FILE
    if not facts.is_file():
        return {}
    lines = [line for line in facts.read_bytes().split(b"\n") if line.strip()]
    return {
        "line_without_newline": sorted(hashlib.sha256(line).hexdigest() for line in lines),
        "line_with_newline": sorted(hashlib.sha256(line + b"\n").hexdigest() for line in lines),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 Private-Database 的 fact 包从对象仓取回并逐条核哈希")
    parser.add_argument("--manifest", required=True,
                        help="sync_private_database.py 写的 manifest.json")
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

    expected = sorted(manifest.get("fact_sha256s") or [])
    if not expected:
        return _fail("MANIFEST_HAS_NO_FACT_HASHES",
                     "这份 manifest 里没有逐条的 fact 哈希——**没有它就没什么可核的**，"
                     "别把「整包哈希对上了」当成「100 条都在」")

    identity = settings.age_identity_file
    if not identity or not Path(identity).is_file():
        return _fail("AGE_IDENTITY_MISSING", "缺少 age 私钥，无法解密")

    receipt = (manifest.get("receipts") or {}).get(args.from_store) or {}
    if receipt.get("status") != "verified":
        return _fail("COPY_NOT_VERIFIED", f"这份 manifest 里没有已验证的 {args.from_store} 副本")
    config = _s3_config(args.from_store)
    if not config:
        return _fail("OBJECT_STORE_NOT_CONFIGURED", f"{args.from_store} 未配置")
    object_key = receipt.get("object_key") or manifest.get("remote_key")
    if not object_key:
        return _fail("OBJECT_KEY_MISSING", "收据里没有 object_key")

    target.mkdir(parents=True, exist_ok=True)
    unpacked = target / "restored-facts"
    with tempfile.TemporaryDirectory(prefix="social-archive-pdb-restore-") as temporary:
        work = Path(temporary)
        ciphertext = work / "facts.tar.gz.age"
        client = _s3_client(config)
        client.download_file(config["bucket"], object_key, str(ciphertext))
        if sha256_file(ciphertext) != manifest["cipher_sha256"]:
            return _fail("CIPHER_SHA256_MISMATCH", "远端密文回读哈希与 manifest 不一致")

        packed = work / "facts.tar.gz"
        completed = subprocess.run(
            ["age", "--decrypt", "--identity", str(identity),
             "--output", str(packed), str(ciphertext)],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0 or not packed.is_file():
            # **不回显 stderr。** 解密失败的输出里可能带密钥材料的片段。
            return _fail("AGE_DECRYPT_FAILED", "age 解密失败", exit_code=completed.returncode)
        if sha256_file(packed) != manifest["original_sha256"]:
            return _fail("PLAINTEXT_SHA256_MISMATCH", "解密后的明文哈希与 manifest 不一致")

        if unpacked.exists():
            shutil.rmtree(unpacked)
        unpacked.mkdir(parents=True)
        with tarfile.open(packed, "r:gz") as archive:
            # `filter="data"` 拒绝绝对路径、`..` 与设备文件——
            # 取回来的包必须只能落在 --target 里面。
            archive.extractall(unpacked, filter="data")

    variants = _hash_variants(unpacked)
    if not variants:
        return _fail("FACTS_FILE_MISSING",
                     f"取回来的包里没有 {FACTS_FILE}", restored_to=str(unpacked))

    matched = next((name for name, digests in variants.items() if digests == expected), None)
    if matched is None:
        # 报的时候用条数最接近的那一种，免得错误信息本身也误导人。
        name, found = min(variants.items(), key=lambda item: abs(len(item[1]) - len(expected)))
        return _fail(
            "FACTS_DO_NOT_MATCH_THE_MANIFEST",
            "取回来的 fact 与 manifest 对不上",
            expected_count=len(expected), restored_count=len(found),
            line_ending_variant_reported=name,
            missing_sample=sorted(set(expected) - set(found))[:3],
            unexpected_sample=sorted(set(found) - set(expected))[:3],
            restored_to=str(unpacked),
        )

    print(json.dumps({
        "status": "PASS",
        "generated_at": utcnow(),
        "source_store": args.from_store,
        "object_key": object_key,
        "restored_to": str(unpacked),
        "fact_count": len(expected),
        "every_fact_hash_matched": True,
        "hashed_as": matched,
        "note": "逐条核过：manifest 里那 %d 条 fact 的 sha256，取回来的包一条不差。"
                % len(expected),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
