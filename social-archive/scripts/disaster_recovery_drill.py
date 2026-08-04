#!/usr/bin/env python3
"""整套灾难恢复演练：**只用远端那三份副本，把档案馆重建出来**（v0.0.0.7 / T16）。

## 它和之前那些演练的区别

  restore_object.py            一个制品能不能取回来
  restore_runtime_db_drill.py  索引能不能取回来并打开
  **这个脚本**                  两样合起来还对不对得上——
                               取回来的索引说有 N 个制品，那 N 个是不是都能取回来、
                               取回来的字节是不是就是索引里登记的那个哈希

前两个各自 PASS，仍然可能拼不成一个档案馆：索引里记着 552 个制品，
而对象仓里少了 3 个——两个演练都不会发现。**这个脚本发现。**

## 做法

1. 用 restore_runtime_db_drill.py 把索引取回来（走完整解密链）。
2. 打开**取回来的那份索引**（不是生产库），列出它记着的每一个制品。
3. 逐个用 restore_object.py `--runtime-db <取回来的索引>` 取回并核对哈希。
4. 汇总：索引说有多少、真取回来多少、哈希对上多少。

**全程只读远端，只写 --target 指定的隔离目录。** 脚本会拒绝数据面下的路径。

## 边界

· 不重建服务、不写回生产、不动任何生产文件。
· 默认全量；`--limit N` 抽样跑，用于快速回归。
· 演练目录跑完不自动删——留给人看。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_archive.config import Settings  # noqa: E402
from social_archive.utils import utcnow  # noqa: E402

HERE = Path(__file__).resolve().parent


def _fail(code: str, message: str, **extra: Any) -> int:
    print(json.dumps({"status": "FAIL", "error_code": code, "message": message,
                      "generated_at": utcnow(), **extra}, ensure_ascii=False))
    return 4


def main() -> int:
    parser = argparse.ArgumentParser(description="只用远端副本重建档案馆并核对")
    parser.add_argument("--manifest", required=True, help="运行库快照的 manifest.json")
    parser.add_argument("--from-store", required=True, choices=("r2", "oci", "github"))
    parser.add_argument("--target", required=True, help="一个全新的隔离目录")
    parser.add_argument("--limit", type=int, default=0, help="只抽这么多个制品（0 = 全量）")
    args = parser.parse_args()

    settings = Settings.from_env()
    target = Path(args.target).expanduser().resolve()
    for guard in (settings.data_root, settings.staging_root, settings.runtime_db.parent):
        if target == guard or guard in target.parents:
            return _fail("RECOVERY_TARGET_INVALID", "演练目标不能落入运行数据面")
    target.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    index_dir = target / "index"
    step = subprocess.run(
        [python, str(HERE / "restore_runtime_db_drill.py"),
         "--manifest", args.manifest, "--from-store", args.from_store,
         "--target", str(index_dir)],
        capture_output=True, text=True, check=False,
    )
    if step.returncode != 0:
        return _fail("INDEX_RESTORE_FAILED", "索引取不回来，后面无从谈起",
                     detail=step.stdout.strip()[-400:] or step.stderr.strip()[-400:])
    restored_db = index_dir / "restored-runtime.sqlite3"
    if not restored_db.is_file():
        return _fail("INDEX_RESTORE_EMPTY", "索引演练报成功，而文件不在——那正是本项目栽过的那种坑")

    connection = sqlite3.connect(f"file:{restored_db}?mode=ro", uri=True)
    try:
        artifact_ids = [row[0] for row in connection.execute("SELECT id FROM artifact ORDER BY id")]
    finally:
        connection.close()
    if args.limit:
        artifact_ids = artifact_ids[: args.limit]

    objects_dir = target / "objects"
    recovered = 0
    failures: list[dict[str, str]] = []
    for artifact_id in artifact_ids:
        run = subprocess.run(
            [python, str(HERE / "restore_object.py"),
             "--artifact-id", artifact_id, "--from-store", args.from_store,
             "--runtime-db", str(restored_db), "--target", str(objects_dir / artifact_id)],
            capture_output=True, text=True, check=False,
        )
        if run.returncode == 0:
            recovered += 1
            continue
        detail = (run.stdout.strip() or run.stderr.strip())[-200:]
        if len(failures) < 20:      # 只留前 20 条样本，别把报告撑爆
            failures.append({"artifact_id": artifact_id, "detail": detail})

    print(json.dumps({
        "status": "PASS" if recovered == len(artifact_ids) else "FAIL",
        "generated_at": utcnow(),
        "source_store": args.from_store,
        "index_says_artifacts": len(artifact_ids),
        "recovered_and_hash_verified": recovered,
        "failed": len(artifact_ids) - recovered,
        "failure_samples": failures,
        "target": str(target),
        "note": "restore_object.py 自己就会比对哈希；这里数的是它判 PASS 的个数。",
    }, ensure_ascii=False))
    return 0 if recovered == len(artifact_ids) else 4


if __name__ == "__main__":
    sys.exit(main())
