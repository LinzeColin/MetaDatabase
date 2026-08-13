r"""AGENTS.md 那张「规矩 / 拦你的那道门」表，点名的门必须真的在（2026-08-14）。

## 它守的是什么

`AGENTS.md` 里那一节的存在理由，它自己写着：

> 它们此前**一条都没写在文档里**，规矩全在门自己肚子里，
> 每个人都得先被拦一次才知道。

也就是说：**这张表是「被拦住的人去哪儿查」的唯一入口**。
它一旦指向一个已经改名或删掉的门，读的人会去找一个不存在的东西——
而这正是这张表要消灭的那种体验。

`check_docs_point_at_things_that_exist.py` 管的是文档里带路径的引用
（`scripts/xxx.py`）。这张表写的是**裸文件名**（`check_docs_match_the_ui.py`、
`test_no_platform_is_invisible_in_the_ui.py`），那道门够不到。

## 顺带钉住一件更要紧的事

2026-08-14 一天新增了七道对写东西的人提要求的门，而它们的规矩当天
**全都只在门肚子里**——接手的人（或 AI）会被拦住却不知道为什么。
所以这里也断言：这张表**不许缩水**（行数只能增不能减到基线以下）。
不是为了凑数，是因为**减少一行的唯一正当理由是那道门没了**，
而那种情况上面第一条就会红。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"

# 2026-08-14 补进七行之后的行数。**只许增。**
MIN_ROWS = 13


def _rule_rows() -> list[str]:
    """那张表的数据行（三列、且第三列点名了 .py）。"""
    rows = []
    for line in AGENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        if ".py" in line:
            rows.append(line)
    return rows


def test_表里点名的每道门都真的在() -> None:
    named: set[str] = set()
    for row in _rule_rows():
        named |= set(re.findall(r"`([A-Za-z0-9_]+\.py)`", row))

    assert named, (
        "那张表里一个 .py 都没扫到。写法变了就把这里一起改——"
        "否则这道判据会对着空集合永远绿。")

    missing = []
    for name in sorted(named):
        found = list((ROOT / "scripts").glob(name)) + list((ROOT / "tests").rglob(name))
        if not found:
            missing.append(name)

    assert not missing, (
        f"这张表点名的门在仓里找不到：{missing}\n"
        "  被它拦住的人会照着这个名字去查，而那个名字不存在——\n"
        "  这正是这张表本来要消灭的那种体验。改名/删门时同步改这里。")


def test_这张表不许缩水() -> None:
    rows = _rule_rows()
    assert len(rows) >= MIN_ROWS, (
        f"这张表现在只有 {len(rows)} 行，低于基线 {MIN_ROWS}。\n"
        "  减少一行的**唯一**正当理由是那道门没了——而那种情况上面那条会先红。\n"
        "  加一道对写东西的人提要求的门，就要在这里补一行：\n"
        "  否则那道门的成本会从「作者一次」变成「以后每个人各一次」。")
