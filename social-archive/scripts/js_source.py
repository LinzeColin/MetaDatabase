#!/usr/bin/env python3
"""读 JS 时把整行注释剔掉——**只有一份实现**（2026-08-10）。

## 为什么单开一个文件

这件事今天在三个地方各被需要一次，而且**两个方向都伤过人**：

  · 错绿：2026-08-06 把悬浮按钮改名，同时在旁边写注释解释为什么改，
    两道文案判据照样绿——它们数到了注释里那个旧名字。
  · 错红：2026-08-10 我把 `SA_OPEN_TASK_CENTER` 那条走不通的路删掉，
    并在注释里写清「原来两处都是
    `chrome.runtime.sendMessage({type:"SA_OPEN_TASK_CENTER"})`」，
    于是 `check_no_mechanism_is_unreachable.py` 报「界面会发它、background
    接不住」——**一道逼人删掉解释性注释的判据，比没有这道判据更坏**。
    同一天我自己新写的结构判据也踩了同一个坑（bridge.js 里一整段解释
    「内容脚本里根本没有 permissions API」的注释被判成违规）。

抄成三份的那天，三份会各自漂。所以放这儿，谁要谁 import。

## 边界

只剔**整行**注释（`//`、`/* … */`、JSDoc 的 `*` 续行、`<!--`）。
行尾注释（`foo(); // 说明`）不剔——剔它要真解析字符串和正则字面量，
而那正是这个仓栽过的地方：一条非锚定的正则直接吃掉了真代码。
**行数保持不变**，好让调用方报得准位置。
"""

from __future__ import annotations

from pathlib import Path


def code_only(source: str | Path) -> str:
    """把整行注释换成空行；行数不变。"""
    text = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
    kept: list[str] = []
    block = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if block:
            kept.append("")
            block = "*/" not in stripped
            continue
        if stripped.startswith("/*"):
            kept.append("")
            block = "*/" not in stripped
            continue
        kept.append("" if stripped.startswith(("//", "*", "<!--")) else line)
    return "\n".join(kept)
