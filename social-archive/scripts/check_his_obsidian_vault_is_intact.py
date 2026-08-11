#!/usr/bin/env python3
r"""东西真的在他 Obsidian 库里，而且是干净的（2026-08-11）。

## 为什么补这一道

整条产品线的终点是这一句：「把你在各个平台收藏的东西，聚到一个自己的资料库里」，
而他把它读到眼睛里的地方是 **Obsidian**。前面每一段都有人验了：

    库里 193 条            ← 部署第 8.8 步
    markdown.zip 193 个    ← 部署第 8.66 步
    桌面那两个双击文件      ← 部署第 8.64 步
    **他库里那 193 篇**     ← 没有任何一步

**而这一段恰恰是这次会话里被弄乱过两次的**（193→198、198→246：
我在服务器上改了文件名，rsync 把新名字带进来，库里于是出现两份）。
每次都是我手工数出来的——手工数不会在下一次部署时自己发生。

## 它怎么验

只读他本机那个目录（`~/Documents/Obsidian/Social Archive`，
和那个双击文件里的默认值同一个），**只数数**：

    篇数 vs 档案馆里的条数     差一条就说差在哪个方向
    空标题                     我在生产上写出过 4 个
    「互动数＋文案＋同一段文案」 抖音那种（判「重复」，不判「以数字开头」）
    作者字段装着点赞数          他那条曾经写着 26.6万
    同一条内容出现多次          文件名尾部那 8 位哈希重复 = 库里有两份

**不读正文、不打印标题、不改任何东西。**

## 库不在的时候

他可能在另一台机器上、或者还没跑过那个双击文件。那种情况**明说是「没有这个库，
跳过」，并且不算通过**——这个仓的规矩是跳过不许伪装成绿。
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = Path.home() / "Documents/Obsidian"
SUBDIR = "Social Archive"


def inspect(folder: Path) -> dict:
    """数一遍那些笔记。**只数数，不取正文。**"""
    files = sorted(folder.rglob("*.md"))
    empty = doubled = like_author = 0
    tails: collections.Counter[str] = collections.Counter()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        heading = re.search(r"^#[ \t]?(.*)$", text, re.M)
        title = (heading.group(1).strip() if heading else "")
        if not title:
            empty += 1
        lead = re.match(r"^\d+(?:\.\d+)?[万千]?", title)
        if lead:
            rest = title[lead.end():]
            half = len(rest) // 2
            if half >= 4 and rest[:half] == rest[half:]:
                doubled += 1
        author = re.search(r'^author:\s*"([^"]*)"', text, re.M)
        if author and re.fullmatch(r"\d+(?:\.\d+)?[万千]?", author.group(1).strip()):
            like_author += 1
        tails[path.name.rsplit("-", 1)[-1]] += 1
    return {
        "notes": len(files),
        "platforms": sorted(p.name for p in folder.iterdir() if p.is_dir()),
        "empty_heading": empty,
        "title_is_a_doubled_caption": doubled,
        "author_is_a_like_count": like_author,
        "same_item_twice": sum(1 for count in tails.values() if count > 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="他 Obsidian 库里那一份是不是好的")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--expect-items", type=int, default=None,
                        help="档案馆里有多少条（给了就比对）")
    args = parser.parse_args()
    folder = Path(args.vault) / SUBDIR

    if not folder.is_dir():
        print(json.dumps({
            "status": "SKIPPED", "vault": str(folder),
            "message_zh": "这台机器上没有那个 Obsidian 库——**这是跳过，不是通过**。"
                          "他可能在另一台机器上，或者还没双击过那个同步文件。",
        }, ensure_ascii=False, indent=2))
        return 0

    measured = inspect(folder)
    problems: list[str] = []
    if not measured["notes"]:
        problems.append("库里那个文件夹在，但一篇笔记都没有")
    if args.expect_items is not None and measured["notes"] != args.expect_items:
        gap = args.expect_items - measured["notes"]
        problems.append(
            f"档案馆里 {args.expect_items} 条，他库里 {measured['notes']} 篇——"
            + (f"少了 {gap} 篇（同步没跑完或没跑过）" if gap > 0
               else f"多了 {-gap} 篇（**多半是重复**，这条链弄乱过两次）"))
    for key, why in (
        ("empty_heading", "空标题（我在生产上写出过 4 个）"),
        ("title_is_a_doubled_caption", "标题是「互动数＋文案＋同一段文案」"),
        ("author_is_a_like_count", "作者字段装着点赞数"),
        ("same_item_twice", "同一条内容在库里有两份"),
    ):
        if measured[key]:
            problems.append(f"{measured[key]} 篇{why}")

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "vault": str(folder), "measured": measured, "problems": problems,
        "boundary_zh": "只读、只数数：不取正文、不打印标题、不改任何东西。",
        "what_this_does_not_prove":
            "不保证每一篇的内容都对——只保证篇数对得上、没有那四类已知的坏形状。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
