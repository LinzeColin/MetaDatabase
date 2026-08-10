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

from social_archive.utils import clean_display_author, clean_display_title  # noqa: E402

HEADING = re.compile(r"^# (.+)$", re.M)
HASH_TAIL = re.compile(r"-([0-9a-f]{8})\.md$")
# 文件名里不能出现的字符（`#` 在 Obsidian 里是标签，`[]` 是链接）
UNSAFE = re.compile(r"[\\/:*?\"<>|#\[\]^]")



def _fit_filename(stem: str, tail: str) -> str:
    """把文件名截到文件系统吃得下的长度——**按字节，不是按字符**。

    2026-08-10 在生产的导出目录上真跑时崩了：

        OSError: [Errno 36] File name too long:
          '…/咕咕嘎嘎😜咕咕嘎嘎🤪…-af61d356.md'

    原来写的是 `[:80]`（80 个**字符**），而 ext4/APFS 限的是 **255 字节**，
    中文 3 字节、emoji 4 字节——80 个字符能到 320 字节。
    他库里就有一个 268 字节的文件名，所以这不是理论问题。

    截的时候不能把一个多字节字符切成两半（那会写出坏文件名），
    所以按 UTF-8 编码逐步退。
    """
    limit = 240 - len(tail.encode("utf-8"))          # 留一点余量给 ext4 的 255
    data = stem.encode("utf-8")
    while len(data) > limit and stem:
        stem = stem[:-1]
        data = stem.encode("utf-8")
    return stem


def repair(root: Path, apply: bool) -> dict[str, int]:
    changed = renamed = dropped = authors_cleaned = 0
    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:                       # 名字太长、权限、坏链……
            # **一个文件坏了不许打死整轮。**（2026-08-10）
            # 生产上就是这样：一个 268 字节的文件名让整个修复崩在第一个文件上，
            # 其余 192 条一条都没修到。
            print(f"  跳过（{error.strerror}）：{path.name[:40]}…")
            continue
        # **作者字段里装着点赞数的，一并清掉。**（2026-08-10）
        # 他那条抖音的 frontmatter 写着 `author: "26.6万"`——那是点赞数。
        # 生产实测：抖音 86 条里 31 条（36%）如此。
        author = re.search(r'^author:\s*"([^"]*)"\s*$', text, re.M)
        if author and clean_display_author(author.group(1)) != author.group(1):
            authors_cleaned += 1
            if apply:
                text = text[:author.start()] + "author: null" + text[author.end():]
                path.write_text(text, encoding="utf-8")
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
        slug = _fit_filename(UNSAFE.sub("", new_title).strip(), f"-{tail.group(1)}.md")
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
            "duplicates_dropped": dropped, "authors_cleaned": authors_cleaned}


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
             if counts['duplicates_dropped'] else "")
          + (f"，{counts['authors_cleaned']} 处作者字段里的点赞数"
             if counts['authors_cleaned'] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
