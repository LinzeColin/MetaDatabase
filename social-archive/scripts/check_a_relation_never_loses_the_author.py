#!/usr/bin/env python3
r"""有没有哪一类收藏，取回来的东西**整类都缺作者**（2026-08-12）。

## 为什么要按「平台 × 关系」拆开看

他生产库里抖音有 54 条缺作者。整体一看像是「有时取得到有时取不到」——
31 条有、54 条没有，同一条取数路（`browser_account_mirror`）。
按 `平台 × 关系` 拆开，再按**产品显示时**的口径算（见下），真相是：

    bilibili  favorite   30 条   真作者 28  (93%)
    bilibili  history    71 条   真作者 70  (99%)
    douyin    favorite   16 条   真作者  0  ← 整类为零
    douyin    like       69 条   真作者  0  ← 也是整类为零（31 条填的是点赞数）
    douyin    saved       1 条   真作者  1  ← 手动保存的，走的另一条路

**抖音那条自动取数路，从来没有取到过一个真作者**——85 条里一个都没有。
而 B 站同一套机制是 93–99%。所以这不是「平台就这样」，是抖音那条路的事。

整体口径看不见这件事：54/86 缺失看起来像「一半左右取不到」，
拆开才看见是**整类为零**。**比例掩盖了分类。**

## 判据

按 `平台 × 关系` 分组算作者填充率。**某一组条数够多（≥5）而填充率为 0 → 红。**

下限取 5 是为了别被一两条噪声打红：1 条缺作者可能只是那条内容本身没作者
（匿名投稿），5 条全缺就不是巧合了。

## 它不保证什么

- **不修**：修要么改取数侧（需要一份真实响应去核字段名，见 kuaishou 那条
  已登记的缺口），要么等他重连后重取。这道门只保证**这件事不会再无声无息**。
- 只看已经进库的东西。一类关系一条都还没同步过，它当然什么也说不出来。

## 口径：按**产品显示时**的那一把尺子算，不是按库里有没有值

第一版我写的是「字段非空就算有作者」，并且在这里白纸黑字写下
「装着点赞数的那一档算『有』——那是另一道门的事」。**那个决定是错的**，
它让这道门去量一件没人关心的事（字段填没填），而不是他真正看得见的事
（那儿写的是不是一个人名）。

实测代价：抖音「点赞」那一类，31 条的 `author_name` 是 `2.2万`、`646`、`8471`
这种**点赞数**。按第一版口径算是 45% 有作者，按显示口径算是 **0%**。

    douyin  favorite   16 条   真作者 0
    douyin  like       69 条   真作者 0（31 条是点赞数，38 条空）
    douyin  saved       1 条   真作者 1  ← 这条是手动保存的，走的另一条路

**真话是「抖音那条自动取数路从来没取到过一个真作者」**，不是「收藏夹丢、点赞一半」。
第一版口径把一个整体为零的事实说成了一个中间数。

所以这里直接用 `clean_display_author`——**资料库页面显示时用的就是它**。
一份文本一把尺子。
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
except NameError:                                # exec 进来的（生产容器 rootfs 只读）
    pass

from social_archive.utils import clean_display_author   # noqa: E402

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
        "select c.platform, r.relation_type, c.author_name"
        " from user_relation r join content c on c.id = r.content_id")
    for platform, relation, author in rows:
        # **按显示口径**：`26.6万` 这种点赞数在页面上是被清掉的，这里也算「缺」。
        shown = clean_display_author(author)
        counts[(platform, relation or "(没记关系)")]["有" if shown else "缺"] += 1

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
