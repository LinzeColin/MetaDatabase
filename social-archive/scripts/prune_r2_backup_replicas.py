#!/usr/bin/env python3
"""按 Owner 定的保留期清理 **R2 上** 的备份副本（默认 3 天）。

## 这条策略是谁定的

同目录的 `prune_runtime_db_snapshots.py` 只清本地，它的文件头明确写着：

    · **不碰远端副本**（R2 / OCI / GitHub）。那三份是灾难恢复用的，
      保留期是另一个决定，Owner 说的是快照本身。

那句话是对的，而它等的那个决定 **2026-08-10 由 Owner 给了：R2 上只留最近 3 天**，
更早的由 OCI（和 GitHub Release）承接。起因是 R2 存储涨到 5.45 GB / 10 GB（54.5%），
而增长几乎全部来自这里：`backups/runtime-db/` 每 15 分钟一份 1.03 MB 快照、
512 份、**从没清理过**，约 +99 MB/天。R2 免费额度只有 10 GB，这样下去必然收费。

## 四条安全底线

1. **删 R2 之前必须先确认 OCI 上有同 key 的对象、且大小一致。**
   这是「卸载」不是「删除」—— 没确认副本还在别处就删，等于数据丢失。
   **确认不了的一律跳过并报出来，绝不因为"应该有"就删。**
2. **最新的那一份永远不删**，哪怕它已超过保留期（同本地脚本的理由：
   一段时间没产出新快照时，那正是最需要它的时候）。
3. **默认只看不删。** 要真删必须显式 `--apply`。删除不可逆。
4. **只碰 `backups/<组>/<时间戳>/` 里的对象。**
   认不出时间戳的一律跳过并报出来 —— **认不出就不动。**

## 它不碰什么

· **不碰 `primary-objects/`** —— 那是制品字节本身（23.5 MB，不增长，且 r2/oci/github 三副本齐全）。
  那是归档内容，不是备份，删它等于毁档。
· **不碰 OCI 和 GitHub 的副本** —— 那正是这些字节要去的地方。
· 不碰本地快照（那是 `prune_runtime_db_snapshots.py` 的事，48 小时）。

## 成本

全部对象都是 `Standard` 存储类，**本脚本绝不产生任何 InfrequentAccess 操作**
（IA 无免费额度且按整计费单位向上取整，51 次操作 = $9.00）。
`ListObjects` 每 1000 个对象 1 次 Class A；`DeleteObject` 是 Class B。
清 800 个对象 ≈ 2 次 Class A + 800 次 Class B，相对免费额度（100 万 / 1000 万每计费周期）可忽略。

## 用法

    python3 scripts/prune_r2_backup_replicas.py                 # 只看会删哪些
    python3 scripts/prune_r2_backup_replicas.py --apply         # 真删
    python3 scripts/prune_r2_backup_replicas.py --hours 168 --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

STAMP = re.compile(r"^(\d{8})T(\d{6})Z$")
DEFAULT_HOURS = 72          # Owner 2026-08-10 定的：R2 上留 3 天
PREFIX = "backups/"
KEEP_PREFIXES = ("primary-objects/",)   # 绝不触碰


def _read_secret(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _client(store_id: str):
    """按 backup.py 的 _s3_config 同一套约定读配置，不抄第二遍逻辑、只抄读法。"""
    p = "SOCIAL_ARCHIVE_" + store_id.upper()
    endpoint = os.getenv(p + "_ENDPOINT", "").strip()
    bucket = os.getenv(p + "_BUCKET", "").strip()
    access = _read_secret(os.getenv(p + "_ACCESS_KEY_ID_FILE"))
    secret = _read_secret(os.getenv(p + "_SECRET_ACCESS_KEY_FILE"))
    region = os.getenv(p + "_REGION", "auto").strip() or "auto"
    style = os.getenv(p + "_ADDRESSING_STYLE", "path").strip() or "path"
    if not all((endpoint, bucket, access, secret)):
        return None, None
    return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access,
                        aws_secret_access_key=secret, region_name=region,
                        config=Config(s3={"addressing_style": style})), bucket


def _stamp_of(key: str) -> datetime | None:
    """key 形如 backups/<组>/<时间戳>/<文件>；取那个时间戳。"""
    parts = key.split("/")
    if len(parts) < 4:
        return None
    found = STAMP.match(parts[2])
    if not found:
        return None
    try:
        return datetime.strptime(found.group(1) + found.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="按保留期清理 R2 上的备份副本")
    ap.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    ap.add_argument("--apply", action="store_true", help="真的删；不给就只看")
    ap.add_argument("--now", default=None)
    args = ap.parse_args()

    r2, r2_bucket = _client("r2")
    oci, oci_bucket = _client("oci")
    if r2 is None or oci is None:
        print(json.dumps({"status": "FAIL", "error_code": "STORE_NOT_CONFIGURED",
                          "r2": r2 is not None, "oci": oci is not None},
                         ensure_ascii=False, indent=2))
        return 2

    now = (datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc) if args.now
           else datetime.now(timezone.utc))
    cutoff = now - timedelta(hours=args.hours)

    objs = []
    for page in r2.get_paginator("list_objects_v2").paginate(Bucket=r2_bucket, Prefix=PREFIX):
        for o in page.get("Contents", []):
            objs.append((o["Key"], o["Size"]))
    if not objs:
        print(json.dumps({"status": "PASS", "message_zh": "R2 上没有 backups/ 对象，无需清理"},
                         ensure_ascii=False, indent=2))
        return 0

    stamped, unrecognised = [], []
    for key, size in objs:
        when = _stamp_of(key)
        (stamped if when else unrecognised).append((key, size, when))
    newest = max((w for _, _, w in stamped), default=None)

    freed = 0
    deleted, kept, skipped_no_replica, failed = [], 0, [], []
    for key, size, when in stamped:
        if any(key.startswith(p) for p in KEEP_PREFIXES):
            kept += 1
            continue
        # 底线 2：最新那一批永远留着
        if newest is not None and when >= newest:
            kept += 1
            continue
        if when >= cutoff:
            kept += 1
            continue
        # 底线 1：OCI 上必须有同 key 同大小的对象，否则不删
        try:
            head = oci.head_object(Bucket=oci_bucket, Key=key)
        except ClientError as exc:
            skipped_no_replica.append({"key": key, "reason": "OCI_HEAD_FAILED",
                                       "detail": exc.response.get("Error", {}).get("Code", "?")})
            continue
        if head["ContentLength"] != size:
            skipped_no_replica.append({"key": key, "reason": "OCI_SIZE_MISMATCH",
                                       "r2_bytes": size, "oci_bytes": head["ContentLength"]})
            continue
        if not args.apply:
            deleted.append(key)
            freed += size
            continue
        try:
            r2.delete_object(Bucket=r2_bucket, Key=key)
            deleted.append(key)
            freed += size
        except ClientError as exc:
            failed.append({"key": key, "error": str(exc)[:120]})

    out = {
        "status": "PASS" if not failed else "PARTIAL",
        "mode": "apply" if args.apply else "dry-run",
        "retention_hours": args.hours,
        "cutoff_utc": cutoff.isoformat(),
        "r2_bucket": r2_bucket,
        "objects_seen": len(objs),
        "deleted_count": len(deleted),
        "kept_count": kept,
        "bytes_freed": freed,
        "mb_freed": round(freed / 2 ** 20, 1),
        "newest_always_kept": newest.strftime("%Y%m%dT%H%M%SZ") if newest else None,
        "skipped_no_verified_replica": skipped_no_replica[:20],
        "skipped_no_verified_replica_count": len(skipped_no_replica),
        "unrecognised_left_alone": [k for k, _, _ in unrecognised][:20],
        "failed": failed[:10],
        "message_zh": ("保留 %d 小时：%d 个对象里%s %d 个，留 %d 个，释放 %.1f MB。"
                       "**最新那一批永远不删。** OCI 上没核对上的 %d 个一律跳过没删。"
                       % (args.hours, len(objs), "删掉" if args.apply else "将删",
                          len(deleted), kept, freed / 2 ** 20, len(skipped_no_replica))),
        "what_this_does_not_touch": "primary-objects/(制品字节，三副本齐全)、OCI 与 GitHub 副本、本地快照",
        "cost_note": "全程 Standard 存储类，零 InfrequentAccess 操作",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
