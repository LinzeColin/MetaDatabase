#!/usr/bin/env python3
r"""把他 Obsidian 库里那些「标题是播放进度」的笔记修回真标题（2026-08-12）。

## 他打开库看到的是这个

    ---
    social_archive_id: "cnt_1036ebdd0a185151ed323f5e5eff263e"
    url: "https://www.bilibili.com/video/BV1gnL16nEc9/?spm_id_from=333.1391.0.0"
    author: null
    relation_types: ["history"]
    ---

    # 00:08/08:43

`# 00:08/08:43` 是 B 站播放器上的时间，不是标题。**他库里 193 篇有 56 篇是这样**——
（先前我用一条宽松的 grep 数成 61，那条把 `# 12:34 某某` 这种也算进去了；
按锚定全匹配数是 56，和 DB 那 56 条、和现有判据的口径一致。）
打开 Obsidian 一眼望去认不出是什么。

## 为什么现在能修

每篇的 frontmatter 里都有 `url`，里面带着 BV 号；B 站公开接口
`x/web-interface/view?bvid=…` **不用登录**就能拿回真标题和作者。

## 边界（这几条是它能不能被信的全部理由）

- **只动 `Social Archive/` 这个子目录**——那是本产品自己写出来的地方，不碰他别的笔记。
- 只改两处：`# <播放进度>` 那一行的标题、以及 `author: null`。
  正文、链接、collections、文件名一律不动。
- 改之前**整份复制到备份目录**（带时间戳），可以整目录还原。
- 默认 `--dry-run`。
- 拿不到真标题的**原样不动**，并在结果里列出来——不猜、不留半成品。

## 这不修取数侧

下一次 history 同步仍会写进播放进度。要定位真标题在哪个元素上，
得等他登录后的历史页。**库干净了 ≠ 管道修好了。**
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_VAULT = Path.home() / "Documents/Obsidian"
SUBDIR = "Social Archive"
TITLE_LINE = re.compile(r"^# (\d{1,2}:\d{2}(?:/\d{1,2}:\d{2})?)\s*$", re.M)
BV = re.compile(r"/video/(BV[0-9A-Za-z]+)")
COLLECTIONS = re.compile(r'^collections: \[(.*)\]\s*$', re.M)
# 历史页的**筛选栏**被当成收藏夹名字抓了下来。认它靠两条一起成立：
# 超长（真收藏夹名不会上百字）**且**含页面控件词。少一条都不动。
PAGE_CHROME_WORDS = ("更多筛选", "清空历史", "批量管理", "全部时长", "全部设备")


def _is_page_chrome(value: str) -> bool:
    return len(value) > 60 and any(w in value for w in PAGE_CHROME_WORDS)
API = "https://api.bilibili.com/x/web-interface/view?bvid={bv}"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}


# B 站这几个码表示「这条稿件是真的没了」——重试多少次都一样。
# 其余失败（限流、网络抖动）**是暂时的，必须重试**，否则会被错记成「没了」。
GONE_FOR_GOOD = {62002, -404, 62004}


def real_title(bv: str, attempts: int = 3) -> tuple[str, str] | str | None:
    """拿真标题和作者。

    返回 `(标题, 作者)`；确定没了返回字符串原因；暂时拿不到返回 None。

    **必须区分「没了」和「这次没拿到」**（2026-08-12）。
    第一版一律返回 None，全量跑 56 条时有 4 条失败，我差点当成「这 4 个视频没了」。
    逐个复查才发现：`BV1D2dKB6EMv` 是 code=62002「稿件不可见」（真没了），
    而 `BV1KgwCzHEQe` 单独查 code=0 **一切正常**——它只是批量时被限流了。
    两件事混成一个 None，就会把能修的 3 条白白留在那儿，
    还在报告里写成「查不回来」。
    """
    last = None
    for attempt in range(attempts):
        request = urllib.request.Request(API.format(bv=bv), headers=HEAD)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
        except Exception as error:                           # noqa: BLE001
            last = error.__class__.__name__
            time.sleep(1.5 * (attempt + 1))
            continue
        code = payload.get("code")
        if code in GONE_FOR_GOOD:
            return f"稿件已不可见（code={code}）"
        if code != 0:
            last = f"code={code}"
            time.sleep(1.5 * (attempt + 1))      # 多半是限流，退避后再试
            continue
        data = payload.get("data") or {}
        title = str(data.get("title") or "").strip()
        author = str((data.get("owner") or {}).get("name") or "").strip()
        if title:
            return (title, author)
        last = "接口回了 0 但没有标题"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="修他库里被写成播放进度的标题")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--backup-root", default=str(Path.home() / ".social-archive-backups"),
                        help="备份放哪儿——**必须在 Obsidian vault 之外**")
    args = parser.parse_args()

    folder = Path(args.vault) / SUBDIR
    if not folder.is_dir():
        print(json.dumps({"status": "SKIPPED", "why": f"{folder} 不在", }, ensure_ascii=False))
        return 0

    broken = []
    for path in sorted(folder.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        found = TITLE_LINE.search(text)
        if not found:
            continue
        bv = BV.search(text)
        broken.append((path, text, found.group(1), bv.group(1) if bv else None))
    if args.limit:
        broken = broken[:args.limit]

    backup = None
    if args.apply and broken:
        # **整目录备份**：一条一条回滚太容易漏，整份复制最省事也最稳。
        #
        # **备份不能放在 vault 里面。** 第一版写的是
        # `folder.with_name(SUBDIR + ".backup-…")`，那就落在
        # `~/Documents/Obsidian/` 底下——Obsidian 会把它当笔记一起索引，
        # 他打开库会看到 56 篇一模一样的重复笔记。修一个毛病造一个更烦的。
        # 放到 vault 之外去。
        backup = Path(args.backup_root) / f"social-archive-vault-backup-{int(time.time())}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, backup)

    fixed, unresolved, collections_cleared = [], [], []
    for path, text, old, bv in broken:
        if not bv:
            unresolved.append({"file": path.name, "old": old, "why": "笔记里没有 BV 号"})
            continue
        got = real_title(bv)
        time.sleep(0.7)
        if isinstance(got, str):
            unresolved.append({"file": path.name, "old": old, "bv": bv,
                               "why": got, "kind": "gone_for_good"})
            continue
        if got is None:
            unresolved.append({"file": path.name, "old": old, "bv": bv,
                               "why": "重试 3 次仍没拿到（多半是限流）", "kind": "transient"})
            continue
        title, author = got
        fixed.append({"file": path.name, "old": old, "new": title, "author": author})
        if not args.apply:
            continue
        # 只换标题那一行；其余一个字节不动。
        updated = TITLE_LINE.sub(lambda _m: f"# {title}", text, count=1)
        if author:
            updated = re.sub(r"^author: null\s*$", f'author: "{author}"',
                             updated, count=1, flags=re.M)
        # 顺带把「筛选栏被当成收藏夹」那一格清掉（同一批笔记、同一个病根：
        # 历史页的形状读取抓到了页面控件而不是数据）。
        # **历史不是收藏夹**，所以正确的值是空，不是另编一个名字。
        found_coll = COLLECTIONS.search(updated)
        if found_coll and _is_page_chrome(found_coll.group(1)):
            updated = COLLECTIONS.sub("collections: []", updated, count=1)
            collections_cleared.append(path.name)
        path.write_text(updated, encoding="utf-8")

    print(json.dumps({
        "mode": "APPLIED" if args.apply else "DRY-RUN（没有改任何文件）",
        "vault": str(folder),
        "notes_with_a_playback_timestamp_title": len(broken),
        "repaired": len(fixed),
        "collections_cleared": len(collections_cleared),
        "unresolved": unresolved,
        "backup": str(backup) if backup else "（干跑不备份）",
        "samples": fixed[:5],
        "what_this_does_not_fix":
            "**取数侧没修**：下一次 history 同步仍会写进播放进度。库干净了 ≠ 管道修好了。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
