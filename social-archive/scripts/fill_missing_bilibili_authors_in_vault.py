#!/usr/bin/env python3
r"""把 B 站笔记里 `author: null` 那些补上作者（2026-08-12）。

## 量到的

他库里 193 篇，**133 篇 `author: null`**。按平台/关系拆开，能不能修分得很干净：

    douyin       like          69 篇   没有 BV 号 → 公开接口修不了
    bilibili     favorite      30 篇   **有 BV 号 → 可修**
    douyin       favorite      16 篇   没有 BV 号 → 修不了
    bilibili     history       15 篇   **有 BV 号 → 可修**
    generic-web  manual_save    2 篇   修不了
    bilibili     watch_later    1 篇   **有 BV 号 → 可修**

也就是 **46 篇能修，87 篇修不了**（抖音没有公开接口，要他的登录态）。

## 和上一次修标题的关系

上一次修的是「标题是播放进度」那 55 篇，顺带把它们的作者补上了。
这一次修的是**标题本来就好、只缺作者**的那些——两批不重叠。

## 边界

- **只补 `author: null` 的**；已经有作者的一个字不动。
- **不碰标题**：这批的标题是好的。
- 只动 `Social Archive/` 子目录；整份备份到 vault 之外。
- 拿不到就跳过并列出来，不猜。
- 默认 `--dry-run`。

## 已经跑过了（2026-08-12）

他库里 `author: null` 从 133 篇降到 90 篇（补了 43 篇）。剩下的 90 篇：
抖音 85 + B 站 3（稿件已删）+ generic-web 2，**都不是这个脚本够得着的**。

上面「量到的」是**动手之前**的实测，留着是为了说明当时的分布，不是待办。
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
BV = re.compile(r"/video/(BV[0-9A-Za-z]+)")
NULL_AUTHOR = re.compile(r"^author: null\s*$", re.M)
API = "https://api.bilibili.com/x/web-interface/view?bvid={bv}"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
GONE_FOR_GOOD = {62002, -404, 62004}


def author_of(bv: str, attempts: int = 3) -> tuple[str, str] | str | None:
    """`(作者, "")` = 拿到了；字符串 = 确定没了；None = 这次没拿到。

    重试与「真没了」的区分，和修标题那次是同一套——上次全量跑 56 条时
    有 3 条只是被限流，混成一个 None 就会被错记成「没了」。
    """
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(API.format(bv=bv), headers=HEAD), timeout=20) as response:
                payload = json.loads(response.read())
        except Exception:                                    # noqa: BLE001
            time.sleep(1.5 * (attempt + 1))
            continue
        code = payload.get("code")
        if code in GONE_FOR_GOOD:
            return f"稿件已不可见（code={code}）"
        if code != 0:
            time.sleep(1.5 * (attempt + 1))
            continue
        name = str(((payload.get("data") or {}).get("owner") or {}).get("name") or "").strip()
        if name:
            return (name, "")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="给缺作者的 B 站笔记补上作者")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--backup-root", default=str(Path.home() / ".social-archive-backups"),
                        help="备份放哪儿——**必须在 Obsidian vault 之外**")
    args = parser.parse_args()

    folder = Path(args.vault) / SUBDIR
    if not folder.is_dir():
        print(json.dumps({"status": "SKIPPED", "why": f"{folder} 不在"}, ensure_ascii=False))
        return 0

    targets = []
    for path in sorted(folder.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not NULL_AUTHOR.search(text):
            continue
        found = BV.search(text)
        if found:
            targets.append((path, text, found.group(1)))
    if args.limit:
        targets = targets[:args.limit]

    backup = None
    if args.apply and targets:
        backup = Path(args.backup_root) / f"social-archive-vault-authors-{int(time.time())}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, backup)

    filled, unresolved = [], []
    for path, text, bv in targets:
        got = author_of(bv)
        time.sleep(0.7)
        if isinstance(got, str):
            unresolved.append({"file": path.name, "bv": bv, "why": got, "kind": "gone_for_good"})
            continue
        if got is None:
            unresolved.append({"file": path.name, "bv": bv,
                               "why": "重试 3 次仍没拿到（多半是限流）", "kind": "transient"})
            continue
        author = got[0]
        filled.append({"file": path.name, "bv": bv, "author": author})
        if args.apply:
            path.write_text(NULL_AUTHOR.sub(f'author: "{author}"', text, count=1),
                            encoding="utf-8")

    print(json.dumps({
        "mode": "APPLIED" if args.apply else "DRY-RUN（没有改任何文件）",
        "notes_missing_an_author_with_a_bv": len(targets),
        "filled": len(filled),
        "unresolved": unresolved,
        "backup": str(backup) if backup else "（干跑不备份）",
        "samples": filled[:5],
        "what_this_does_not_fix":
            "抖音那 85 篇（like 69 / favorite 16）没有公开接口，"
            "要 Owner 的登录态才拿得到作者——这一批**动不了**，如实记着。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
