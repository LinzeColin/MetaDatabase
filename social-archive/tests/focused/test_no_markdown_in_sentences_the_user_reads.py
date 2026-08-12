"""接口下发给用户看的句子里，不许有 Markdown 记号（2026-08-10）。

## 它拦的是什么

档案馆那张导出卡片直接显示服务端下发的 `last_message_zh` / `next_action_zh`，
而界面是 `escapeHtml` 之后当**纯文本**画的。服务端却在句子里写了 `**…**`：

    Obsidian 已连接  **还有 192 条从来没送到这里。**  已送到这里 1 / 193 条。

生产实测（2026-08-10 问 `/v1/destinations`）：**obsidian 与 archivebox 都带着它**
——而 Owner 那两个正好都是 `connected/enabled`。他点开导出那一屏，
最要紧的那句话外面挂着一对原样的星号。

同一条动线上还有第二处：他点「把没送过去的 N 条补上」之后弹的那句
`已排队 N 条。**排队不等于送到**——…`（api.py）。

## 为什么此前没人发现

这个仓**已经有**一条查 Markdown 残留的判据——但它查的是使用说明那一页
（`pwa_render_drill` 的 `leftover_markdown: /\\*\\*|^\\s*\\|/m`）。
**没有人查过接口下发的文案。** 而 `**` 在这个仓的注释里到处都是
（写给读代码的人看的），一不小心就滑进了给用户看的那一半。

## 怎么查

用 `ast` 只取**真正的字符串常量**（注释天然不在里面），
再排掉文档字符串（那是写给读代码的人的）。剩下的里面，
**同时含中文和 `**` 的**就是嫌疑：面向用户的中文句子不该带排版记号。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src/social_archive"

CHINESE = re.compile(r"[一-鿿]")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """文档字符串是写给读代码的人的，允许带记号。"""
    marked: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                marked.add(id(body[0].value))
    return marked


def _offending() -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                              # noqa: PERF203
            continue
        skip = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in skip:
                continue
            # **SQL 里的 `--` 注释是写给读代码的人的**，不是用户看的字。
            # db.py 那条大查询里全是它们，第一版把整条 SQL 报成了违规。
            text = "\n".join(
                line for line in node.value.splitlines()
                if not line.strip().startswith(("--", "#"))
            ) if "\n" in node.value else node.value
            if "**" in text and CHINESE.search(text):
                hits.append((str(path.relative_to(ROOT)), node.lineno, text[:70]))
    return hits


def test_the_scanner_sees_string_constants_at_all() -> None:
    """反空扫：连一个中文字符串常量都取不到的话，下面那条会白过。"""
    found = 0
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                              # noqa: PERF203
            continue
        skip = _docstring_nodes(tree)
        found += sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in skip and CHINESE.search(node.value)
        )
    assert found >= 50, f"只取到 {found} 个中文字符串常量——这条判据在空扫"


def test_no_user_facing_sentence_carries_markdown() -> None:
    hits = _offending()
    assert not hits, (
        "接口下发给用户看的句子里有 Markdown 记号，而界面是当纯文本画的："
        + "；".join(f"{path}:{line} {text!r}" for path, line, text in hits)
        + "——他看到的是一对原样的星号。`**` 在这个仓的注释里到处都是，"
        "一不小心就滑进给用户看的那一半。")
