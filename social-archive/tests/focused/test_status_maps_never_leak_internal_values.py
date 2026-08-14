"""状态映射不许兜底成内部值（2026-08-07）。

## 这次是怎么发现的

让弹窗那个演练把**账号卡片本身**也读回来（原来只读顶上那三句），
第一次跑就看见 Owner 会看到的那一行：

    小 我 1 条 · 同步时间没有记录 disconnected

`statusName` 里没有 `disconnected`，而

    statusName[current] || current

**安静地兜底成英文原文**。兜底本身没错——少一个键时给个东西总比空白好；
错的是它**不出声**，而且给出的那个东西是内部值。

## 为什么不去枚举「服务端到底有哪些状态」

那才是最想要的判据，但**服务端没有一份权威的状态表**：状态经常是变量
（`final_status = "blocked_environment" if … else ("partial" if … else "completed")`）
写进去的，grep 取不全。而**取不全的词表会做出一道分母不全的门**——
它会一直绿，直到某个没数到的状态真的出现在他眼前。这个仓在"分母"上栽过很多次。

所以换一条守得住的：**兜底不许是那个值本身**。不论服务端将来多出什么状态，
他看到的至少是一句中文，而不是 `blocked_environment`。

平台名／目的地名不在这条规则里：那些的 id（`bilibili`、`obsidian`）
本身就是可读的词，而且它们的覆盖由 `check_every_platform_table_is_complete.py` 管。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI_DIRS = ("apps/browser-extension", "apps/pwa")

# 名字里带这些词的映射表 = 状态类。它们的值是内部枚举，露给用户就是英文。
STATUS_MAP = re.compile(r"\b(\w*(?:status|state|connection)\w*)\s*\[", re.I)
# `xxx[expr] || expr` —— 同一个 expr 兜底给自己
FALLBACK_TO_SELF = re.compile(
    r"(\w+)\s*\[\s*([\w.?\[\]'\"]+?)\s*\]\s*\|\|\s*\2(?![\w.])")


def _ui_lines() -> list[tuple[Path, int, str]]:
    out = []
    for directory in UI_DIRS:
        for path in sorted((ROOT / directory).glob("*.js")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                out.append((path, number, line))
    return out


def test_the_scan_sees_ui_files() -> None:
    """**先证明这条判据数得到东西。** 扫到 0 个文件的判据永远是绿的。"""
    lines = _ui_lines()
    assert len({path for path, _, _ in lines}) >= 5, "界面文件一个都没扫到"
    assert any("statusName" in line for _, _, line in lines), (
        "连 statusName 都没扫到——扫描范围不对")


def test_no_status_map_falls_back_to_the_raw_value() -> None:
    offenders = []
    for path, number, line in _ui_lines():
        for match in FALLBACK_TO_SELF.finditer(line):
            name = match.group(1)
            if STATUS_MAP.match(f"{name}["):
                offenders.append(f"{path.name}:{number}  {match.group(0)}")
    assert not offenders, (
        "**状态映射兜底成了内部值**——少一个键，用户就看到一个英文单词，"
        "而且它不出声：\n  " + "\n  ".join(offenders)
        + "\n兜底给一句中文（比如「状态未知」），别把枚举值印给他。")
