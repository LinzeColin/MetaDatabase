#!/usr/bin/env python3
r"""生产上不许有第二个同名的运行库（2026-08-11）。

## 撞见它的经过

查另一件事时随手看了一眼容器里的运行库，得到：

    /var/lib/social-archive/social-archive.sqlite3            **0 字节**
    /var/lib/social-archive/runtime/social-archive.sqlite3     4,952,064 字节（193 条）

**同名，差一层目录，一个是空的。** 我第一次查就猜了上面那个路径，
拿到 `no such table: content`，差点把它当成「生产的库坏了」。

今天两侧都核过，容器和宿主机的 `Settings.from_env()` **都指向下面那个真的**
（4.7 MB / 193 条），所以那个空文件现在是死的、不影响任何人。
**但它是个绊索**：它就躺在最容易被猜到的那个路径上，
下一个工具、下一个人（或者下一次的我）指过去，会读到一个空库，
然后如实报出「0 条」——一个看起来完全合理的错答案。

这个仓已经吃过同一形状的亏：**同一份 schema 包里两份、只改了产物那份**。

## 判据

`/var/lib/social-archive` 底下，凡是**和真运行库同名**的 `.sqlite3`，
只允许存在真的那一个。多出来的（尤其 0 字节的）就报出来，
并说清它危险在哪、该怎么处置——**不自己删**：生产上的东西先查清是不是活的，
删是 Owner 的决定。

只读、只数数：不打开任何一个库、不读任何一行内容。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INSIDE = r'''
import glob, json, os
from social_archive.config import Settings

real = str(Settings.from_env().runtime_db)
name = os.path.basename(real)
root = "/var/lib/social-archive"
same_name = sorted(
    p for p in glob.glob(os.path.join(root, "**", name), recursive=True)
    if os.path.isfile(p))
print(json.dumps({
    "real": real,
    "real_bytes": os.path.getsize(real) if os.path.exists(real) else None,
    "same_name_files": [{"path": p, "bytes": os.path.getsize(p)} for p in same_name],
}, ensure_ascii=False))
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="生产上有没有第二个同名运行库")
    parser.add_argument("--host", default=None)
    parser.add_argument("--container", default="social-archive-core-api-1")
    args = parser.parse_args()
    host = args.host or (ROOT / "deploy/PRODUCTION_HOST").read_text(encoding="utf-8").strip()

    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host,
         f"sudo docker exec -i {args.container} python -"],
        input=INSIDE, capture_output=True, text=True, check=False)
    payload = None
    for line in reversed(done.stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
            break
        except ValueError:
            continue
    if payload is None:
        print(json.dumps({"status": "FAIL", "error_code": "NO_JSON_FROM_CONTAINER",
                          "detail": (done.stdout + done.stderr)[-400:]},
                         ensure_ascii=False, indent=2))
        return 2

    real = payload.get("real")
    others = [f for f in payload.get("same_name_files", []) if f["path"] != real]
    problems: list[str] = []
    if not payload.get("real_bytes"):
        problems.append(f"真运行库 {real} 是空的或不在——这是最要紧的一条")
    for extra in others:
        problems.append(
            f"{extra['path']}（{extra['bytes']} 字节）和真运行库同名——"
            "**它躺在最容易被猜到的那个路径上**：谁指过去就会读到一个空库，"
            "然后如实报出「0 条」。**别自己删**（生产上的东西先查是不是活的），"
            "确认没人用之后由 Owner 决定处置。")

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "host": host, "measured": payload, "problems": problems,
        "boundary_zh": "只读、只数数：不打开任何一个库、不读任何一行内容。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
