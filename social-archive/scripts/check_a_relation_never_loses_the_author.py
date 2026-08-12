#!/usr/bin/env python3
r"""有没有哪一类收藏，取回来的东西**整类都缺作者**（2026-08-12）。

## 为什么要按「平台 × 关系」拆开看

他生产库里抖音有 54 条缺作者。整体一看像是「有时取得到有时取不到」——
31 条有、54 条没有，同一条取数路（`browser_account_mirror`）。
按关系类型拆开，形状立刻变了：

    douyin  favorite   16 条，**0 条有作者**
    douyin  like       69 条，31 条有作者
    douyin  saved       1 条，有作者

**收藏夹那一类是整类为零，不是概率问题。** 而抖音**只同步 `favorite` 这一类**
（`SCANNABLE_RELATIONS["douyin"] == ("favorite",)`）——也就是说他连上抖音之后
新进来的每一条，作者栏都会是空的。

整体口径看不见这件事：54/86 缺失看起来像"一半左右取不到"，
而真相是"有一整类一条都取不到"。**比例掩盖了分类。**

## 判据

按 `平台 × 关系` 分组算作者填充率。**某一组条数够多（≥5）而填充率为 0 → 红。**

下限取 5 是为了别被一两条噪声打红：1 条缺作者可能只是那条内容本身没作者
（匿名投稿），5 条全缺就不是巧合了。

## 它不保证什么

- **不修**：修要么改取数侧（需要一份真实响应去核字段名，见 kuaishou 那条
  已登记的缺口），要么等他重连后重取。这道门只保证**这件事不会再无声无息**。
- 只看已经进库的东西。一类关系一条都还没同步过，它当然什么也说不出来。
- 作者字段装着点赞数的那一档算「有」——那是另一道门（`clean_display_author`）的事。
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys

DB = "/var/lib/social-archive/runtime/social-archive.sqlite3"

# 某一组要多少条才值得判。太小会被一两条匿名内容打红。
ENOUGH_TO_JUDGE = 5


def main() -> int:
    parser = argparse.ArgumentParser(description="有没有哪一类收藏整类都缺作者")
    parser.add_argument("--db", default=DB)
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--host", default="",
                        help="给了就把自己送进那台机器的容器里跑（库只在容器里）")
    args = parser.parse_args()

    if args.host:
        # **容器的 rootfs 是只读的**，`docker cp` 进不去，所以把自己 base64 送进去
        # 用 `python3 -c` 跑。这样判据只有一份实现，不用在部署脚本里再抄一遍 SQL。
        import base64
        import pathlib
        import shlex
        import subprocess
        source = pathlib.Path(__file__).read_text(encoding="utf-8")
        blob = base64.b64encode(source.encode()).decode()
        inner = (f"import base64,sys;sys.argv=['chk'{',\"--brief\"' if args.brief else ''}];"
                 f"exec(base64.b64decode('{blob}'))")
        done = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=25", args.host,
             f"sudo docker exec social-archive-core-api-1 python3 -c {shlex.quote(inner)}"],
            capture_output=True, text=True, timeout=180)
        sys.stdout.write(done.stdout)
        sys.stderr.write(done.stderr)
        return done.returncode

    connection = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    counts: dict[tuple[str, str], dict[str, int]] = collections.defaultdict(
        lambda: {"有": 0, "缺": 0})
    rows = connection.execute(
        "select c.platform, r.relation_type,"
        " case when c.author_name is null or trim(c.author_name)='' then '缺' else '有' end"
        " from user_relation r join content c on c.id = r.content_id")
    for platform, relation, has in rows:
        counts[(platform, relation or "(没记关系)")][has] += 1

    problems, table = [], []
    for (platform, relation), seen in sorted(counts.items()):
        total = seen["有"] + seen["缺"]
        rate = seen["有"] / total if total else 0.0
        table.append({"platform": platform, "relation": relation, "items": total,
                      "with_author": seen["有"], "fill_rate": round(rate, 3)})
        if total >= ENOUGH_TO_JUDGE and seen["有"] == 0:
            problems.append(
                f"**{platform} 的「{relation}」整类都没有作者**（{total} 条，一条都没有）"
                "——不是概率问题，是这一类的取数路没把作者带回来。"
                "他连上之后新进来的还是会缺。"
            )

    payload = {
        "status": "FAIL" if problems else "PASS",
        "groups": table,
        "problems": problems,
        "message_zh": ("每一类收藏都至少取回了一部分作者。" if not problems
                       else "有整类缺作者的——见 problems。"),
        "what_this_does_not_prove":
            "只看已经进库的。某一类一条都还没同步过时，这道门什么也说不出来。",
    }
    if args.brief:
        print(f"  {'PASS · ' if not problems else 'FAIL · '}"
              f"按平台×关系分了 {len(table)} 组")
        for line in problems:
            print(f"    {line}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
