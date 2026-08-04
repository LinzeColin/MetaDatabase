#!/usr/bin/env python3
"""把**一条真实内容**从头到尾追一遍（v0.0.0.7 / T17）。

## 为什么写它

交接表上 T17 一直是 pending，理由写着「黄金事务按定义需要一次真实平台取数，
因此在 T06/T08 解开之前无法开始」，而同一行里又写着
**「Acceptance 原文不在仓内」**。

也就是说，那个「按定义」引用的是一份谁也读不到的定义。
在这上面停着不动，等于拿一个无法查证的前提去挡住一整格。

**能量的先量。** 生产库里就有带着制品与投递回执的真实内容（douyin），
于是这个脚本把一条内容在每一站的凭据逐个取出来：

    内容记录 → 观测（怎么来的） → 制品（哈希、字节数、状态）
      → 三仓副本（逐个 verified） → 投递回执（去了哪、什么时候）
      → **从远端真取回来一次并核哈希**

最后那一步是要害：前面几步都是读数据库自述，只有它是**真的把字节
从异地取回来重新算了一遍哈希**。

## 它证明什么、不证明什么

证明：取得之后的每一站都通，而且能从异地把字节拿回来。
不证明：取得那一站。这条内容是 v0.0.0.6 时期入库的，不是这一版
      现场抓的——**这正是 T17 还缺的那一环**，脚本会在结论里明说。

## 用法

    python3 scripts/golden_transaction_trace.py --db <运行库> [--content-id ...]
    # 不给 --content-id 就自动挑一条「制品与投递回执都有」的

## 边界

· **只读生产**：除了 --restore-target 指定的隔离目录，什么都不写。
· 不改数据库、不改文件、不发任何请求到平台。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _rows(connection: sqlite3.Connection, sql: str, *params: Any) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(sql, params)]


def _pick_content(connection: sqlite3.Connection) -> str | None:
    found = _rows(connection, """
        SELECT c.id FROM content c
        WHERE (SELECT COUNT(*) FROM artifact a WHERE a.content_id = c.id) > 0
          AND (SELECT COUNT(*) FROM destination_receipt r
               WHERE r.content_id = c.id AND r.status = 'done') > 0
        ORDER BY c.id LIMIT 1
    """)
    if found:
        return found[0]["id"]
    # 没有 done 的就退一步，任何回执都行——**并且把这件事说出来**，
    # 不能让「挑到的这条其实没投递成功」混在报告里看不出来。
    loose = _rows(connection, """
        SELECT c.id FROM content c
        WHERE (SELECT COUNT(*) FROM artifact a WHERE a.content_id = c.id) > 0
          AND (SELECT COUNT(*) FROM destination_receipt r WHERE r.content_id = c.id) > 0
        ORDER BY c.id LIMIT 1
    """)
    return loose[0]["id"] if loose else None


def main() -> int:
    parser = argparse.ArgumentParser(description="把一条真实内容从头到尾追一遍")
    parser.add_argument("--db", required=True, help="运行库路径（只读打开）")
    parser.add_argument("--content-id", default=None)
    parser.add_argument("--from-store", default="r2", choices=("r2", "oci", "github"))
    parser.add_argument("--restore-target", default=None,
                        help="取回演练目录；不给就用临时目录，跑完删")
    parser.add_argument("--skip-restore", action="store_true",
                        help="只读数据库那几站，不真去远端取（排查时用）")
    args = parser.parse_args()

    database = Path(args.db).expanduser()
    if not database.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "DB_MISSING",
                          "detail": str(database)}, ensure_ascii=False))
        return 2
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)

    try:
        content_id = args.content_id or _pick_content(connection)
        if not content_id:
            print(json.dumps({"status": "FAIL", "error_code": "NO_TRACEABLE_CONTENT",
                              "message_zh": "库里没有一条同时带着制品与投递回执的内容。"},
                             ensure_ascii=False))
            return 4

        content = _rows(connection, "SELECT * FROM content WHERE id = ?", content_id)
        if not content:
            print(json.dumps({"status": "FAIL", "error_code": "CONTENT_NOT_FOUND",
                              "detail": content_id}, ensure_ascii=False))
            return 4
        row = content[0]
        observations = _rows(
            connection,
            "SELECT id, connector_id, observed_at, payload_sha256 FROM observation "
            "WHERE content_id = ? ORDER BY observed_at", content_id)
        artifacts = _rows(
            connection,
            "SELECT id, artifact_type, archive_level, sha256, byte_size, status, created_at "
            "FROM artifact WHERE content_id = ? ORDER BY id", content_id)
        replicas = {
            artifact["id"]: _rows(
                connection,
                "SELECT store_id, status, object_key, verified_sha256, original_sha256, encryption "
                "FROM object_replica WHERE artifact_id = ? ORDER BY store_id", artifact["id"])
            for artifact in artifacts
        }
        receipts = _rows(
            connection,
            "SELECT destination_id, status, remote_path, finished_at, error_code, message_zh "
            "FROM destination_receipt WHERE content_id = ? ORDER BY finished_at", content_id)
    finally:
        connection.close()

    problems: list[str] = []
    if not artifacts:
        problems.append("这条内容一个制品都没有")
    for artifact in artifacts:
        got = replicas[artifact["id"]]
        verified = [r["store_id"] for r in got if r["status"] == "verified"]
        if len(verified) < 3:
            problems.append(
                f"制品 {artifact['id']} 只有 {len(verified)} 份已核副本（{verified}）")
        # **两个哈希是两件事，别拿错。** 第一版把 verified_sha256 当成制品哈希去比，
        # 六条副本全报「对不上」——而数据是好的：
        #   original_sha256  = 明文（制品本身）的哈希    → 必须等于 artifact.sha256
        #   verified_sha256  = 上传上去那个**密文**的哈希 → 与明文不同是正常的
        # 实测：三个仓的 verified_sha256 完全一样（同一个加密块传了三处），
        # 于是这里顺手多守一条更强的：**三处存的确实是同一份字节。**
        for replica in got:
            if replica["original_sha256"] and replica["original_sha256"] != artifact["sha256"]:
                problems.append(
                    f"制品 {artifact['id']} 在 {replica['store_id']} 登记的明文哈希对不上制品本身")
        ciphers = {r["verified_sha256"] for r in got if r["verified_sha256"]}
        if len(ciphers) > 1:
            problems.append(
                f"制品 {artifact['id']} 在各仓的密文哈希不一致（{sorted(ciphers)}）——"
                "三份副本存的不是同一份字节")
    # 回执的成功态是 `done`（生产实测词表只有 done / failed 两个）。
    # 第一版按 `delivered` 判，于是一条投递成功的记录被报成失败。
    delivered = [r for r in receipts if r["status"] == "done"]
    if not delivered:
        problems.append(f"没有一条投递成功的回执（拿到的状态：{[r['status'] for r in receipts]}）")

    # ---- 最后一站：真把字节从异地取回来 ----
    restore: dict[str, Any] = {"ran": False}
    if not args.skip_restore and artifacts:
        target = Path(args.restore_target) if args.restore_target else Path(
            tempfile.mkdtemp(prefix="sa-golden-"))
        artifact_id = artifacts[0]["id"]
        run = subprocess.run(
            [sys.executable, str(HERE / "restore_object.py"),
             "--artifact-id", artifact_id, "--from-store", args.from_store,
             "--runtime-db", str(database), "--target", str(target / artifact_id)],
            capture_output=True, text=True, check=False)
        restore = {
            "ran": True, "artifact_id": artifact_id, "store": args.from_store,
            "exit_code": run.returncode,
            "detail": (run.stdout.strip() or run.stderr.strip())[-300:],
        }
        if run.returncode != 0:
            problems.append(f"从 {args.from_store} 取回 {artifact_id} 失败——"
                            "前面几站都是数据库自述，只有这一站是真的把字节拿回来")
        if not args.restore_target:
            shutil.rmtree(target, ignore_errors=True)

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "content": {
            "id": row["id"], "platform": row["platform"],
            "title": (row["title"] or "")[:60],
            "canonical_url": row["canonical_url"],
            "first_observed_at": row["first_observed_at"],
        },
        "how_it_was_observed": observations,
        "artifacts": [
            {**artifact,
             "replicas": [{"store": r["store_id"], "status": r["status"],
                           "encryption": r["encryption"]} for r in replicas[artifact["id"]]]}
            for artifact in artifacts
        ],
        "delivery_receipts": receipts,
        "restored_from_remote_and_hash_checked": restore,
        "problems": problems,
        "what_this_does_not_cover": (
            "**取得那一站**。这条内容是既有入库数据，不是这一版现场从平台抓的——"
            "那正是 T17 还缺的一环，要等 Owner 那次诊断把平台接口地址固化下来。"
        ),
    }, ensure_ascii=False, default=str))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
