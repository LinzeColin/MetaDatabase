#!/usr/bin/env python3
"""从远端把运行库快照取回来，验它真的能打开（v0.0.0.7 / INV-REVERSIBLE）。

## 为什么单独有这个演练

backup_runtime_db.py 证明的是「快照做出来了、传上去了、密文读回来一致」。
**那三件事都成立，快照仍然可能是个打不开的文件**——密文哈希一致只说明
字节没坏，不说明解密之后是一个能用的 SQLite。

这一天里已经吃过两次同形状的亏：
  · 三份副本全登记 verified，而 GitHub 那条取回路根本跑不通
  · 恢复报 `target_written: true`，而目标目录是空的（PrivateTmp）

所以这里做完整的一路：**下载 → 解密 → 解压 → 打开 → 数表 → 判它是不是他的数据**。

## 2026-08-11：前四道都真，最后一道原来是空的

第一次真跑（生产机上，从 R2 取）当场量出两个自己的毛病：

  · **远端那份不见了的时候，它抛 botocore 回溯**——部署日志里读到的是 Python 栈，
    没有结构化结果。而「manifest 说在、远端拿不到」恰恰是这个演练最要紧的一条红。
  · **只要解密出来是个合法 SQLite 就报 PASS**：缺表会被 `_counts` 悄悄省掉键，
    空库会得到 `content: 0` 而没人看它。同一天我在生产上刚留下过一个 0 字节的
    同名运行库——备份对着那个路径拍一张，这里就会绿着说「取回来了」。

两个都已修，并且各自有反例：注入非法哈希 / 不存在的对象名 / 把判据改反，都真的变红。

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
from github_release_backup import (  # noqa: E402  复用同一套 gh 调用，不抄第二遍
    github_cli_environment,
    run as run_gh,
    verify_draft_release,
    verify_private_repository,
)
from social_archive.config import Settings  # noqa: E402
from social_archive.utils import sha256_file, utcnow  # noqa: E402

# 拿来对照的表。挑的是「丢了就说不出这些制品是什么」的那几张。
COMPARED_TABLES = ("content", "user_relation", "artifact", "object_replica", "destination_receipt")


def _fail(code: str, message: str, **extra: Any) -> int:
    print(json.dumps({"status": "FAIL", "error_code": code, "message": message,
                      "generated_at": utcnow(), **extra}, ensure_ascii=False))
    return 4


def _counts(database: Path) -> dict[str, int | None]:
    """每张表都给一个格子；**表不在就写 null，不许把它从字典里省掉**。

    2026-08-11 之前这里写的是 `for table in ... if table in present`——
    表没了就悄悄少一个键，而下游只是把这个字典打印出来。
    也就是说一份丢了四张表的快照会照样报 PASS。
    （`empty-default-swallows-unknown`：`[]`/缺键都会被读成「没问题」。）
    """
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        present = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            table: (int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    if table in present else None)
            for table in COMPARED_TABLES
        }
    finally:
        connection.close()


def judge(restored: dict[str, int | None], live: dict[str, int | None]) -> list[str]:
    """取回来的这份，**是不是他的数据**——不只是「打得开」。

    这个演练原来的绿只说明「解密出来是一个合法的 SQLite」。
    一个**空的**合法 SQLite 完全过得去——而这不是假想：
    2026-08-11 我自己就在生产上留下过一个 0 字节的同名运行库
    （见 `check_no_decoy_runtime_db_on_production.py`）。备份哪天对着那个路径
    拍一张，这里就会取回一个能打开、一条内容都没有的库，然后报 PASS。
    """
    problems: list[str] = []
    absent = [table for table, rows in restored.items() if rows is None]
    if absent:
        problems.append(
            f"取回来的库里没有这几张表：{'、'.join(absent)}——"
            "**能打开不等于是他的数据**；缺表意味着这份快照重建不出档案馆。")
    if restored.get("content") == 0:
        problems.append(
            "取回来的库打得开，但**一条内容都没有**——"
            "这正是「对着一个空库拍了快照」的样子（生产上出现过同名空库）。")
    for table, rows in restored.items():
        here = live.get(table)
        if rows is None or here is None or rows >= here:
            continue  # 快照比线上少几行是正常的（它是那一刻的样子）
        if rows * 2 < here:
            problems.append(
                f"{table}：线上 {here} 行，快照里只有 {rows} 行——"
                "**少了一半以上**，不像「这十几分钟写进去的」，像快照本身缺了东西。")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="把运行库快照从对象仓取回并验证它打得开")
    parser.add_argument("--manifest", required=True, help="backup_runtime_db.py 写的 manifest.json")
    # **github 也要能验。** 「登记成 verified」和「取得回来」是两件事——
    # 这一天已经因为这个区别撞过两次（GitHub 制品取回路两个致命缺陷、
    # 恢复报 target_written 而目录是空的）。第三份副本不能只验到密文层。
    parser.add_argument("--from-store", required=True, choices=("r2", "oci", "github"))
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

    github_receipt = (manifest.get("receipts") or {}).get("github") or {}
    if args.from_store == "github":
        if github_receipt.get("status") != "verified":
            return _fail("GITHUB_COPY_NOT_VERIFIED",
                         "这份 manifest 里没有已验证的 GitHub 副本")
        config = None
    else:
        config = _s3_config(args.from_store)
        if not config:
            return _fail("OBJECT_STORE_NOT_CONFIGURED", f"{args.from_store} 未配置")

    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="social-archive-db-restore-") as temporary:
        work = Path(temporary)
        ciphertext = work / "snapshot.gz.age"
        if args.from_store == "github":
            # object_key 形如 gh-release://<owner>/<repo>/<tag>#<资产名>
            raw = str(github_receipt.get("object_key") or "")
            try:
                location, member = raw.split("#", 1)
                _, rest = location.split("gh-release://", 1)
                owner, repo, tag = rest.split("/", 2)
            except ValueError:
                return _fail("GITHUB_RECEIPT_INVALID", "GitHub 副本收据格式非法")
            repository = f"{owner}/{repo}"
            environment = github_cli_environment(settings.github_token_file)
            if environment is None or not shutil.which("gh"):
                return _fail("GITHUB_CLI_UNAVAILABLE", "缺少 gh 或 GitHub 令牌，无法取回")
            verify_private_repository(repository, env=environment)
            verify_draft_release(repository, tag, env=environment)
            download_dir = work / "gh"
            download_dir.mkdir(parents=True, exist_ok=True)
            run_gh(["gh", "release", "download", tag, "--repo", repository,
                    "--dir", str(download_dir)], env=environment)
            fetched = download_dir / member
            if not fetched.is_file():
                return _fail("GITHUB_ASSET_MISSING", "Draft Release 里找不到那份密文")
            shutil.copyfile(fetched, ciphertext)
        else:
            client = _s3_client(config)
            try:
                client.download_file(config["bucket"], manifest["object_key"], str(ciphertext))
            except Exception as exc:  # noqa: BLE001 —— 远端取不到有一百种异常，都是同一个结论
                # **这是这个演练能报出的最要紧的一条红。** 2026-08-11 实测：
                # 把 object_key 改成一个不存在的键，它原来是抛一个 botocore 的
                # 长回溯出来（部署日志里读到的是 Python 栈，不是「那份副本不见了」），
                # 而且 stdout 上没有任何结构化结果，上游没法判读。
                code = ""
                response = getattr(exc, "response", None)
                if isinstance(response, dict):
                    code = str((response.get("Error") or {}).get("Code") or "")
                return _fail(
                    "SNAPSHOT_MISSING_FROM_STORE",
                    f"manifest 说这份快照在 {args.from_store} 上，而**远端拿不到它**——"
                    "这正是这个演练存在的理由：登记成功和取得回来是两件事。",
                    object_key=manifest["object_key"],
                    error_type=exc.__class__.__name__, error_code_from_store=code)
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
    problems = judge(restored_counts, live_counts)
    payload = {
        "status": "FAIL" if problems else "PASS",
        "generated_at": utcnow(),
        "source_store": args.from_store,
        "object_key": manifest["object_key"],
        "restored_to": str(restored),
        "restored_byte_size": restored.stat().st_size,
        "restored_counts": restored_counts,
        "live_counts_now": live_counts,
        "problems": problems,
        "note": "快照是取快照那一刻的样子；此后写入的行自然不在里面，所以两边计数可以不同。",
    }
    if problems:
        payload["error_code"] = "RESTORED_DB_IS_NOT_HIS_DATA"
    print(json.dumps(payload, ensure_ascii=False))
    return 4 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
