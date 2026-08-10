#!/usr/bin/env python3
r"""把一堆导出的 Markdown 里那种「互动数 + 文案 + 文案」的标题修掉。

## 为什么要单独一个脚本

`clean_display_title` 已经接进了服务端的渲染，但**服务器上已经生成的那批
文件是修复之前写的**。而部署卡在主机磁盘上（5G 闸门），重新生成不了。

于是拉到本机的那一份仍然是脏的。2026-08-10 因为这个出过一次事故：
我在他库里手工修好 47 个标题（连文件名一起换），**接着又跑了一次同步脚本**，
rsync 把服务器上那份脏的又加了回来——同一条内容出现两个文件，
他库里的 md 从 194 变成 241。**是我把他的库弄乱的。**

修法不是"记得别重跑"，是**让同步脚本在合并进库之前先修**。这个脚本就是那一步。

## 它做什么

对给定目录下每个 .md：
  · 读第一行 `# 标题`，用 `clean_display_title` 修
  · 改了的话，同时把文件名前半段换掉（保留 `-<8位hex>.md` 那个尾巴，
    那是内容 id 的短哈希，是去重的依据）

**只改能自证的那一档**（去掉纯数字前缀后左右两半完全相同），其余一个字不动。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.utils import clean_display_title      # noqa: E402

HEADING = re.compile(r"^# (.+)$", re.M)
HASH_TAIL = re.compile(r"-([0-9a-f]{8})\.md$")
# 文件名里不能出现的字符（`#` 在 Obsidian 里是标签，`[]` 是链接）
UNSAFE = re.compile(r"[\\/:*?\"<>|#\[\]^]")


def repair(root: Path, apply: bool) -> dict[str, int]:
    changed = renamed = dropped = 0
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        found = HEADING.search(text)
        if not found:
            continue
        old_title = found.group(1).strip()
        new_title = clean_display_title(old_title)
        if new_title == old_title:
            continue
        changed += 1
        if apply:
            path.write_text(text[:found.start(1)] + new_title + text[found.end(1):],
                            encoding="utf-8")
        tail = HASH_TAIL.search(path.name)
        if not tail:
            continue
        slug = UNSAFE.sub("", new_title).strip()[:80]
        if not slug:
            continue
        target = path.with_name(f"{slug}-{tail.group(1)}.md")
        if target.name == path.name:
            continue
        if target.exists():
            # **正确命名的那一份已经在了 —— 这一份是重复的。**（2026-08-10）
            # 不删的话：每次同步都把服务器上的旧名字带回来，改完标题却因为
            # 「目标已存在」跳过重命名，两份并存且标题都干净，去重也分不出该删谁。
            # Owner 库里因此从 193 涨到 246、52 个重复，**而且稳定在错的状态**——
            # 那比一次性弄乱更坏，因为看起来「跑完了」。
            dropped += 1
            if apply:
                path.unlink()
            continue
        renamed += 1
        if apply:
            path.rename(target)
    return {"titles_repaired": changed, "files_renamed": renamed,
            "duplicates_dropped": dropped}


def main() -> int:
    parser = argparse.ArgumentParser(description="修掉导出 Markdown 里重复的标题")
    parser.add_argument("directory")
    parser.add_argument("--apply", action="store_true", help="真改；不给就只报数")
    args = parser.parse_args()
    root = Path(args.directory).expanduser().resolve()
    if not root.is_dir():
        print(f"不是一个目录：{root}", file=sys.stderr)
        return 2
    counts = repair(root, args.apply)
    verb = "已修" if args.apply else "将修"
    print(f"  {verb} {counts['titles_repaired']} 个标题，"
          f"{counts['files_renamed']} 个文件名"
          + (f"，清掉 {counts['duplicates_dropped']} 个重复文件"
             if counts['duplicates_dropped'] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
