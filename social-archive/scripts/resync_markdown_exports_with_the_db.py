#!/usr/bin/env python3
r"""让磁盘上那批导出的 Markdown 跟上库里已经修好的标题和作者（2026-08-12）。

## 为什么它们会对不上

`/v1/library/markdown.zip` —— 他点「下载全部 Markdown」拿到的那个包 ——
**只读 `exports/markdown` 下的文件，不现算**。那批文件是**入库当时**写下来的，
后来我把库里的标题修回了真标题，磁盘上这一份没人管。

于是同一条内容，资料库页面上是真标题，他下载下来的 zip 里还是 `00:37/02:46`。
部署第 8.66 步就是在这里打红的。

## 为什么不去重新检测一遍，而是照着库抄

因为库那一份**已经核对过了**：11 条抓重的逐条比过他笔记里的原文（11/11 一致），
5 条带小时的播放进度是拿 BV 号从 B 站公开接口查回来的。再在文件上跑一遍检测，
等于把同一件事判两次——**两把尺子早晚会不一样**（今天已经因此撞了三次）。

照着 `social_archive_id` 抄，是确定性的，不联网，也不会有第二套判据。

## 文件名也要跟着改

导出那一侧按 `safe_slug(标题)-<id 后 8 位>.md` 起名。只改标题不改名，
**下一次导出会照新标题写出一批新文件，旧的原地不动** —— 同一条内容两份。
他这个库被弄乱过两次（193→198→246），就是这个形状。

## 边界

- **只改 frontmatter 的 `author` 和那一行 `# 标题`，以及文件名。**
- **正文一个字不动。** 有些条目的正文里也重复着那串时间码——那是抓下来的原文，
  是内容不是元数据，改它超出「修元数据」的范围。如实留着。
- 库里没有这条 id 的文件**跳过并列出来**，不猜。
- 默认干跑，先把要改的每一条打出来。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
except NameError:                                            # exec 进来的（生产容器 rootfs 只读）
    pass

from social_archive.utils import clean_display_author, safe_slug   # noqa: E402

DB = "/var/lib/social-archive/runtime/social-archive.sqlite3"
EXPORTS = "/var/lib/social-archive/exports/markdown"
ID_LINE = re.compile(r'^social_archive_id:\s*"([^"]+)"\s*$', re.M)
AUTHOR_LINE = re.compile(r"^author:\s*.*$", re.M)
TITLE_LINE = re.compile(r"^# (.+)$", re.M)
# 地址在导出文件里出现**两处**：frontmatter 的 `url:` 和正文那行「原始链接：」。
# 只改一处，他打开的那份就会自己和自己不一致。
URL_FRONT = re.compile(r"^url:\s*.*$", re.M)
URL_BODY = re.compile(r"^原始链接：.*$", re.M)


def main() -> int:
    parser = argparse.ArgumentParser(description="让导出的 Markdown 跟上库里的标题和作者")
    parser.add_argument("--apply", action="store_true", help="真的写文件（默认只看不改）")
    parser.add_argument("--db", default=DB)
    parser.add_argument("--exports", default=EXPORTS)
    args = parser.parse_args()

    folder = Path(args.exports)
    if not folder.is_dir():
        print(json.dumps({"status": "SKIPPED", "why": f"{folder} 不在"}, ensure_ascii=False))
        return 0

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = {row[0]: {"title": row[1], "author": row[2], "url": row[3]}
            for row in con.execute(
                "select id, title, author_name, canonical_url from content")}

    retitled, reauthored, relinked, renamed, unknown = [], [], [], [], []
    for path in sorted(folder.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        found = ID_LINE.search(text)
        if not found:
            unknown.append({"file": path.name[:44], "why": "文件里没有 social_archive_id"})
            continue
        row = rows.get(found.group(1))
        if row is None:
            unknown.append({"file": path.name[:44], "why": "库里没有这条 id（可能已被删除）"})
            continue

        # **标题要压成一行再写。**（2026-08-13）
        #
        # 库里有一条标题带着换行（`…说个鬼故事\n\nDeepSeek V4 Flash 只有…`）。
        # Markdown 的 `# ` 只能占一行——原样写下去，那个文件的标题行会断成三段，
        # 后面两段变成正文。**只看不改那一跑把它照出来了**，否则我就把他一个
        # 文件写坏了。页面上不受影响（显示走 clean_display_title），
        # 所以库里的原值不动，只在写文件这一步压平。
        title = " ".join(str(row["title"] or "").split())
        updated = text
        current = TITLE_LINE.search(text)
        if title and current and current.group(1).strip() != title:
            updated = TITLE_LINE.sub(lambda _m: f"# {title}", updated, count=1)
            retitled.append({"file": path.name[:36], "old": current.group(1)[:30], "new": title[:36]})

        # **按产品显示时的口径写，不是库里的原始值。**
        # 抖音有 31 条的 author_name 装着点赞数（`26.6万`）。资料库页面靠
        # `clean_display_author` 在显示时清掉，库里原值不动——这是 2026-08-10 定的规矩。
        # 我第一版直接把原值抄进了文件，于是 31 个文件的作者字段变成了点赞数：
        # **页面上看不见的东西，被我写进了他下载下来的那个包里。**
        # 清出来是空的也要写回去（写成 `null`），**不能只在有值时才动**——
        # 我第一版就是这样，于是上一轮误写进去的 31 个点赞数原地留着，
        # 「只在有值时覆盖」把清除这个动作整个漏掉了。
        author = clean_display_author(row["author"])
        wanted = (f"author: {json.dumps(author, ensure_ascii=False)}" if author
                  else "author: null")
        existing = AUTHOR_LINE.search(updated)
        if existing and existing.group(0) != wanted:
            updated = AUTHOR_LINE.sub(lambda _m: wanted, updated, count=1)
            reauthored.append({"file": path.name[:36], "author": author[:30] or "（清空：那是点赞数）"})

        # **地址也要跟上。**（2026-08-13）
        #
        # 2026-08-13 把库里 127 条地址上的埋点洗掉了
        # （`spm_id_from` / `source=Baiduspider-sdc`），而磁盘上这批文件
        # 是入库当时写的——不同步的话，他下载下来的那个包里还是脏地址，
        # 和资料库页面上显示的对不上。**和标题那件事是同一个形状。**
        url = str(row["url"] or "").strip()
        if url:
            want_front = f"url: {json.dumps(url, ensure_ascii=False)}"
            want_body = f"原始链接：{url}"
            before = updated
            if URL_FRONT.search(updated):
                updated = URL_FRONT.sub(lambda _m: want_front, updated, count=1)
            if URL_BODY.search(updated):
                updated = URL_BODY.sub(lambda _m: want_body, updated, count=1)
            if updated != before:
                relinked.append({"file": path.name[:36], "url": url[:56]})

        if args.apply and updated != text:
            path.write_text(updated, encoding="utf-8")

        # 文件名跟着标题走——不改的话下一次导出会多写一份出来。
        if title:
            tail = path.stem.rsplit("-", 1)[-1]
            target = path.with_name(f"{safe_slug(title, tail)}-{tail}.md")
            if target != path and not target.exists():
                renamed.append({"from": path.name[:40], "to": target.name[:40]})
                if args.apply:
                    path.rename(target)

    print(json.dumps({
        "mode": "APPLIED" if args.apply else "DRY-RUN（没有改任何文件）",
        "files": len(list(folder.rglob("*.md"))),
        "rows_in_the_database": len(rows),
        "titles_brought_up_to_date": len(retitled),
        "authors_brought_up_to_date": len(reauthored),
        "urls_brought_up_to_date": len(relinked),
        "files_renamed_to_match_the_title": len(renamed),
        "not_in_the_database": unknown,
        "samples_retitled": retitled[:4],
        "samples_renamed": renamed[:3],
        "samples_relinked": relinked[:3],
        "what_this_does_not_touch":
            "正文。有些条目的正文里也重复着那串时间码——那是抓下来的原文，是内容不是元数据。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
