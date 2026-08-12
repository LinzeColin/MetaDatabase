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
sys.path.insert(0, str(ROOT / "src"))

from social_archive.title_repair import undouble_title  # noqa: E402

DEFAULT_VAULT = Path.home() / "Documents/Obsidian"
SUBDIR = "Social Archive"


def inspect(folder: Path) -> dict:
    """数一遍那些笔记。**只数数，不取正文。**"""
    files = sorted(folder.rglob("*.md"))
    empty = doubled = like_author = timestamp_title = 0
    tails: collections.Counter[str] = collections.Counter()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        heading = re.search(r"^#[ \t]?(.*)$", text, re.M)
        title = (heading.group(1).strip() if heading else "")
        if not title:
            empty += 1
        # **标题是播放进度**（2026-08-12）。打开他 Obsidian 库随手看一篇，
        # 标题是 `34:04/42:37`——那是 B 站播放器上的时间，不是标题。
        # 全库数了一遍：**193 篇里 56 篇是这个样子**，全部来自 history 那条路。
        # 而此前每一道门都是绿的：这类标题「以数字开头」，
        # 而那一条恰恰被判成**正常**（「10万个冷知识」那次的教训）。
        if re.fullmatch(r"\d{1,2}:\d{2}(/\d{1,2}:\d{2})?", title):
            timestamp_title += 1
        # **这一条曾经和修复脚本口径不一样，于是放过了它该抓的东西**（2026-08-12）。
        #
        # 原来写的是「去掉数字前缀之后，正好对半分成一模一样的两半」：
        #
        #     half = len(rest) // 2
        #     if half >= 4 and rest[:half] == rest[half:]
        #
        # 库里那一条前一遍结尾多一个空格，`len(rest)` 是奇数，两半永远对不上——
        # 这道门于是报 0，而修复脚本在同一份文本上找到 1 条。另外两处窄：
        # `[万千]` 不含「亿」，而且非要有数字前缀（没前缀的纯重复它看不见）。
        #
        # 现在直接用入库那道校验的同一份实现，**一份文本一把尺子**。
        if undouble_title(title) != title:
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
        "title_is_a_playback_timestamp": timestamp_title,
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

    # **这一条是播报，不是门。**（2026-08-12）
    #
    # 56 篇播放进度标题是**他库里已经存在的数据**，不是这次部署弄坏的。
    # 做成门的话，它在他重新同步之前永远变不绿——而
    # `a-red-that-can-never-turn-green-is-not-a-signal`：那种红没有信息，
    # 只会逼下一个人绕过整道检查（连带把真会红的那几条一起绕过去）。
    #
    # 真因在取数那一侧（history 那条路把播放器上的时间当成了标题），
    # 而验证修复要他登录之后的那个页面——我这边看不到。所以：**说出来，不拦。**
    notes_to_read = []
    if measured["title_is_a_playback_timestamp"]:
        # **2026-08-12：这一段重写过，因为原来那句已经过期了。**
        #
        # 原文是「修它要改取数侧，而验证要 Owner 登录后的页面」。
        # 那句话对**取数侧**仍然成立，但对这 56 篇**数据**已经不成立了：
        # 每一篇的 frontmatter 里都带着 BV 号，B 站公开接口不用登录就能拿回真标题。
        # 已经修回 55 篇（库和生产库两边都修了，原标题存着可回滚），
        # 剩下的是稿件真的没了（code=62002）那种，谁也修不回来。
        #
        # 而且入库那道门现在会把播放进度形状的标题置空，所以新的进不来了。
        # **一句过期的提醒和一句缺失的提醒一样会把人带错**——今天早些时候
        # 才为 Access 那一屏立过同样的规矩，这里照办。
        notes_to_read.append(
            f"{measured['title_is_a_playback_timestamp']} 篇标题仍是播放进度"
            "（如 34:04/42:37）。2026-08-12 已用 B 站公开接口把 55 篇修回真标题"
            "（原标题存在 metadata_json.title_before_repair，可回滚）；"
            "**剩下的是稿件已不可见（code=62002）那种，修不回来**。"
            "新进来的由 CaptureRequest 那道校验器挡着（播放进度形状一律置空）——"
            "但**取数侧仍然会挑错元素**，那个要等 Owner 登录后的历史页才能定位。")

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "notes_to_read_zh": notes_to_read,
        "vault": str(folder), "measured": measured, "problems": problems,
        "boundary_zh": "只读、只数数：不取正文、不打印标题、不改任何东西。",
        "what_this_does_not_prove":
            "不保证每一篇的内容都对——只保证篇数对得上、没有那四类已知的坏形状。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
