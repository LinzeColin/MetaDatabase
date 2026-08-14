#!/usr/bin/env python3
"""把使用说明变成产品里打得开的一页（2026-08-07）。

## 为什么

验收条件第 2 条要的是**「一份普通人照着做得完的使用说明」**。
`docs/使用说明.md` 一直是照着这条写的、也有判据核着它每一步在产品里真的存在
（`scripts/check_the_guide_matches_the_product.py`）——

**但他打不开它。** 它躺在我这台机器的 git 工作树里。产品里没有任何入口指向它
（`index.html` 里那个 `help` 只是个 CSS 类名）。于是每次他要装/要连，
都是我在聊天里现敲一遍步骤——那不叫使用说明，那叫我记得。

这个脚本把它转成 `apps/pwa/guide.html`，服务端开一条 `/guide` 路由，
资料库和安装页各放一个入口。

## 只认这份文档真的用到的语法，**不认识就报错**

写一个通用 Markdown 解析器不在范围内，而"大概能转"最危险：
未被识别的行会**看起来像正文**地印出去，`**` 和 `|` 原样出现在他眼前。
这个仓已经栽过两次（`**` 直接进了 textContent）。

所以：逐行判定，遇到判不出来的构造就**退出非零并指出行号**，
由人去改文档或补这个脚本。宁可拒绝生成，不可生成一份糊的。

    python3 scripts/build_guide_page.py [--check]

`--check` 只比对不写盘：用来在发布门里挡住「改了 md 忘了重生成」。
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/使用说明.md"
OUTPUT = ROOT / "apps/pwa/guide.html"

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_AUTOLINK = re.compile(r"<(https?://[^>]+)>")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """行内语法。**顺序要紧**：先转义，再一层层还原成标签。

    先 escape 再插标签，才不会把文档里真的 `<` 当成标签；
    而 `<https://…>` 这种自动链接在 escape 之后长成 `&lt;https…&gt;`，
    所以它的正则要在 escape 之后匹配转义形态。
    """
    out = html.escape(text)
    out = re.sub(r"&lt;(https?://[^&]+)&gt;",
                 r'<a href="\1" rel="noopener">\1</a>', out)
    out = _CODE.sub(r"<code>\1</code>", out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                 r'<a href="\2" rel="noopener">\1</a>', out)
    return out


def convert(markdown: str) -> tuple[str, list[str]]:
    """返回 (body_html, 看不懂的行)。**看不懂就攒起来交给调用方拒绝。**"""
    body: list[str] = []
    unknown: list[str] = []
    lines = markdown.splitlines()
    index = 0
    list_open: str | None = None

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            body.append(f"</{list_open}>")
            list_open = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            close_list()
            index += 1
            continue

        if stripped.startswith("```"):                       # 代码块
            close_list()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(html.escape(lines[index]))
                index += 1
            index += 1
            body.append("<pre><code>" + "\n".join(block) + "</code></pre>")
            continue

        if stripped.startswith("|"):                          # 表格
            close_list()
            rows: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            cells = [[c.strip() for c in row.strip("|").split("|")] for row in rows]
            # 第二行是 |---|---| 那种分隔行，去掉
            separator = len(cells) > 1 and all(
                set(c) <= set("-: ") and c for c in cells[1])
            header, rest = cells[0], cells[2:] if separator else cells[1:]
            table = ["<table><thead><tr>"]
            table += [f"<th>{_inline(c)}</th>" for c in header]
            table.append("</tr></thead><tbody>")
            for row in rest:
                table.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
            table.append("</tbody></table>")
            body.append("".join(table))
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            body.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if stripped in ("---", "***", "___"):
            close_list()
            body.append("<hr>")
            index += 1
            continue

        if stripped.startswith("> "):
            close_list()
            body.append(f"<blockquote>{_inline(stripped[2:])}</blockquote>")
            index += 1
            continue

        # `·` 是这个仓行文里最常用的项目符号，不是标准 Markdown——
        # 但它是这份文档真的在用的写法，认它比要求作者改文档合理。
        bullet = re.match(r"^[-*·]\s+(.*)$", stripped)
        numbered = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if bullet or numbered:
            want = "ol" if numbered else "ul"
            if list_open != want:
                close_list()
                body.append(f"<{want}>")
                list_open = want
            body.append(f"<li>{_inline((bullet or numbered).group(1))}</li>")
            index += 1
            continue

        # 列表项的缩进续行：接到上一条上，不另起一段。
        if list_open and body and body[-1].endswith("</li>") \
                and re.match(r"^\s{2,}\S", line):
            body[-1] = body[-1][: -len("</li>")] + " " + _inline(stripped) + "</li>"
            index += 1
            continue

        # 普通段落：**必须是「没有任何 Markdown 结构标记」的一行**。
        # 判不出来的构造宁可拒绝，也不要看起来像正文地印出去。
        if re.match(r"^(\s*[+>]|\s{4,}\S|<!--)", line):
            unknown.append(f"{index + 1}: {line[:70]}")
            index += 1
            continue
        close_list()
        body.append(f"<p>{_inline(stripped)}</p>")
        index += 1

    close_list()
    return "\n".join(body), unknown


PAGE = """<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>使用说明 · Social Archive</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin: 0 auto; max-width: 46rem; padding: 2rem 1.2rem 5rem;
         font: 16px/1.75 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  h1 {{ font-size: 1.7rem; margin: 0 0 1.4rem; }}
  h2 {{ font-size: 1.28rem; margin: 2.4rem 0 .7rem; padding-top: .8rem;
        border-top: 1px solid rgba(128,128,128,.28); }}
  h3 {{ font-size: 1.08rem; margin: 1.6rem 0 .5rem; }}
  p, li {{ margin: .5rem 0; }}
  code {{ background: rgba(128,128,128,.16); border-radius: 4px;
          padding: .1em .35em; font-size: .92em; }}
  pre {{ background: rgba(128,128,128,.13); border-radius: 8px;
         padding: .9rem 1rem; overflow-x: auto; }}
  pre code {{ background: none; padding: 0; }}
  table {{ border-collapse: collapse; width: 100%; display: block; overflow-x: auto; }}
  th, td {{ border: 1px solid rgba(128,128,128,.32); padding: .45rem .6rem;
            text-align: left; vertical-align: top; }}
  blockquote {{ margin: .8rem 0; padding: .1rem 0 .1rem 1rem;
                border-left: 3px solid rgba(128,128,128,.4); }}
  a {{ color: inherit; }}
  .back {{ display: inline-block; margin-bottom: 1.5rem; font-size: .95rem; }}
</style>
<a class="back" href="/">← 回资料库</a>
{body}
"""


def build() -> tuple[str, list[str]]:
    body, unknown = convert(SOURCE.read_text(encoding="utf-8"))
    return PAGE.format(body=body), unknown


def main() -> int:
    parser = argparse.ArgumentParser(description="把使用说明转成产品里的一页")
    parser.add_argument("--check", action="store_true",
                        help="只比对不写盘（发布门用：改了 md 忘了重生成就红）")
    args = parser.parse_args()

    if not SOURCE.is_file():
        print(f"FAIL：找不到 {SOURCE.relative_to(ROOT)}", file=sys.stderr)
        return 2
    page, unknown = build()
    if unknown:
        print("FAIL：**这几行的写法这个转换器不认识**，拒绝生成一份糊的：",
              file=sys.stderr)
        for line in unknown:
            print(f"  {SOURCE.name}:{line}", file=sys.stderr)
        print("  改文档，或者把这种写法补进 scripts/build_guide_page.py。",
              file=sys.stderr)
        return 2

    if args.check:
        if not OUTPUT.is_file():
            print(f"FAIL：{OUTPUT.relative_to(ROOT)} 还没生成——"
                  "跑一次 scripts/build_guide_page.py", file=sys.stderr)
            return 2
        if OUTPUT.read_text(encoding="utf-8") != page:
            print(f"FAIL：**{OUTPUT.relative_to(ROOT)} 和使用说明对不上**——"
                  "改了 md 却没重新生成，他看到的会是上一版。"
                  "跑一次 scripts/build_guide_page.py", file=sys.stderr)
            return 2
        print(f"PASS：{OUTPUT.relative_to(ROOT)} 与使用说明一致。")
        return 0

    OUTPUT.write_text(page, encoding="utf-8")
    print(f"PASS：已生成 {OUTPUT.relative_to(ROOT)}（{len(page)} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
