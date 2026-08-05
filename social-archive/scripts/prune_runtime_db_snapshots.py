#!/usr/bin/env python3
"""按 Owner 定的保留期清理运行库快照（v0.0.0.7 / T16）。

## 这条策略是谁定的

`backup_runtime_db.py` 一直**故意不删**，它的文件头写着：

    **不删旧快照。** 保留策略是运维决定，这里只管产出；
    自动删除历史备份是那种「出事才发现」的操作，不该由脚本自作主张。

那句话是对的，而它等的那个决定 2026-08-06 由 Owner 给了：**保留 48 小时**。
所以清理这件事从「脚本自作主张」变成了「照他说的做」——这个脚本只做那一件事。

## 三条安全底线

1. **最新的那一份永远不删**，哪怕它已经超过保留期。
   否则一段时间没产出新快照，这个脚本会把最后一份也清掉——
   而那正是最需要它的时候。
2. **默认只看不删。** 要真删必须显式 `--apply`。
   删除不可逆，而一个默认就删的脚本，跑错一次没有后悔药。
3. **只碰这一个目录里、名字长得像时间戳的子目录**。
   认不出名字的一律跳过并报出来——**认不出就不动**。

## 它不碰什么

· **不碰远端副本**（R2 / OCI / GitHub）。那三份是灾难恢复用的，
  保留期是另一个决定，Owner 说的是快照本身。
· 不碰制品的 CAS，也不碰任何加密对象。

## 用法

    python3 scripts/prune_runtime_db_snapshots.py                  # 只看会删哪些
    python3 scripts/prune_runtime_db_snapshots.py --apply          # 真删
    python3 scripts/prune_runtime_db_snapshots.py --hours 72 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STAMP = re.compile(r"^(\d{8})T(\d{6})Z$")
DEFAULT_HOURS = 48          # Owner 2026-08-06 定的


def _parse(name: str) -> datetime | None:
    found = STAMP.match(name)
    if not found:
        return None
    try:
        return datetime.strptime(found.group(1) + found.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def _dir_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="按保留期清理运行库快照")
    parser.add_argument("--root", default="/var/lib/social-archive/backups/runtime-db")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    parser.add_argument("--apply", action="store_true", help="真的删；不给就只看")
    parser.add_argument("--now", default=None, help="把「现在」固定成某个时刻（判据用）")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "SNAPSHOT_ROOT_MISSING",
                          "root": str(root)}, ensure_ascii=False, indent=2))
        return 2

    now = (datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc) if args.now
           else datetime.now(timezone.utc))
    cutoff = now - timedelta(hours=args.hours)

    dated: list[tuple[datetime, Path]] = []
    unrecognised: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        when = _parse(child.name)
        if when is None:
            unrecognised.append(child.name)      # **认不出就不动**
            continue
        dated.append((when, child))

    if not dated:
        print(json.dumps({"status": "FAIL", "error_code": "NO_SNAPSHOTS_RECOGNISED",
                          "unrecognised": unrecognised,
                          "message_zh": "一份认得出的快照都没有——**这不是「已经清干净了」**，"
                                        "多半是目录或命名变了。"}, ensure_ascii=False, indent=2))
        return 4

    dated.sort()
    newest = dated[-1][1]
    doomed = [path for when, path in dated if when < cutoff and path != newest]
    kept = [path for when, path in dated if path not in doomed]

    freed = 0
    removed: list[str] = []
    for path in doomed:
        size = _dir_bytes(path)
        if args.apply:
            shutil.rmtree(path)
            removed.append(path.name)
        freed += size

    print(json.dumps({
        "status": "PASS",
        "applied": args.apply,
        "retention_hours": args.hours,
        "cutoff_utc": cutoff.isoformat(),
        "total_before": len(dated),
        "would_remove" if not args.apply else "removed": [p.name for p in doomed],
        "kept": len(kept),
        "newest_always_kept": newest.name,
        "bytes_freed" if args.apply else "bytes_would_free": freed,
        "unrecognised_left_alone": unrecognised,
        "message_zh": (
            f"保留 {args.hours} 小时：{len(dated)} 份里"
            f"{'删掉' if args.apply else '可以删'} {len(doomed)} 份，留 {len(kept)} 份。"
            f"**最新那份（{newest.name}）永远不删。**"
            + ("" if args.apply else " —— 这次只看没删，要真删加 --apply。")),
        "what_this_does_not_touch": "远端三副本（R2 / OCI / GitHub）没有动——那是另一个保留期决定。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
