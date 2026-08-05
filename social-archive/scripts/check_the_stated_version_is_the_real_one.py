#!/usr/bin/env python3
"""**版本只有一个真源，其他地方都必须跟它一样**（v0.0.0.7 / T18）。

## 为什么

2026-08-05 顺手数了一遍全仓文档提到的版本号，数出三处不成立的事实：

  · `README.md` 第 1 行写着 `# Social Archive v0.0.0.6` —— 仓是 0.0.0.7
  · `AGENTS.md` 第 9 行写着 `- 版本：v0.0.0.6` —— **而 AGENTS.md 是给
    接手的 agent 读的那一份**，每一个后来的人都会被它告知一个错的版本
  · `CHANGELOG.md` 最新一节是 v0.0.0.4 —— v5、v6、v7 三个版本一条都没有

没有一处是「坏了」的样子。改版本号的时候，代码里那几处会因为跑不起来
而被发现，文档里这几处不会——**它们只会安静地说一个两版之前的事实**。

## 真源是 `pyproject.toml`

不是因为它更权威，是因为**必须挑一个**。挑好之后其余全部对它，
包括 `src/social_archive/__init__.py`、扩展的 `manifest.json`、
README 的标题、AGENTS 的身份段。

## 顺带查 CHANGELOG 有没有当前版本这一节

「这一版改了什么」这件事，出问题那天是要翻的。三个版本没有条目，
翻的人只会以为最后一次改动是 v0.0.0.4。

**它只查有没有这一节，不查内容对不对**——后者没法自动化，
也不该假装能。

## 边界

· 只查**声明版本**的地方，不查正文里顺口提到旧版本的地方。
  「v0.0.0.6 当时是这么做的」是历史叙述，不是错。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 真源。改版本从这里改起。
SOURCE_OF_TRUTH = ("pyproject.toml", re.compile(r'^version\s*=\s*"([0-9.]+)"', re.M))

# (文件, 抓版本的正则, 这地方为什么要紧)
MUST_AGREE = [
    ("src/social_archive/__init__.py", re.compile(r'^__version__\s*=\s*"([0-9.]+)"', re.M),
     "包自己报的版本；上报、日志、诊断里都带着它"),
    ("apps/browser-extension/manifest.json", None,
     "Owner 装的那个扩展报的版本；他截图给你看的就是这个数"),
    ("README.md", re.compile(r"^#\s+Social Archive v([0-9.]+)", re.M),
     "仓库的门面，第一行"),
    ("AGENTS.md", re.compile(r"^-\s*版本：`v([0-9.]+)`", re.M),
     "**接手的 agent 读的那一份**——它说错，后面每一个人都被告知错的版本"),
]


def _fail(problems: list[str]) -> int:
    print(f"**不合格 {len(problems)} 处**：")
    for item in problems:
        print(f"  {item}")
    print("  ↳ 改版本时，代码里那几处会因为跑不起来被发现；文档里这几处不会，"
          "它们只会安静地说一个旧版本。")
    return 1


def main() -> int:
    name, pattern = SOURCE_OF_TRUTH
    path = ROOT / name
    if not path.is_file():
        print(f"真源 {name} 不在，跳过——**这不是通过**。")
        return 0
    found = pattern.search(path.read_text(encoding="utf-8"))
    if not found:
        print(f"在 {name} 里找不到版本声明，跳过——**这不是通过**。")
        return 0
    truth = found.group(1)

    problems: list[str] = []
    checked = 0
    for target, target_pattern, why in MUST_AGREE:
        target_path = ROOT / target
        if not target_path.is_file():
            problems.append(f"{target} 不在——它本该声明版本（{why}）")
            continue
        text = target_path.read_text(encoding="utf-8")
        if target_pattern is None:                       # manifest.json 按 JSON 读
            try:
                stated = json.loads(text).get("version")
            except json.JSONDecodeError as error:
                problems.append(f"{target} 不是合法 JSON：{error}")
                continue
        else:
            match = target_pattern.search(text)
            stated = match.group(1) if match else None
        checked += 1
        if stated is None:
            problems.append(f"{target} 里找不到版本声明——{why}")
        elif stated != truth:
            problems.append(f"{target} 说版本是 {stated}，而 {name} 说是 {truth}——{why}")

    changelog = ROOT / "CHANGELOG.md"
    if changelog.is_file():
        checked += 1
        if not re.search(rf"^##\s+v{re.escape(truth)}\b", changelog.read_text(encoding="utf-8"), re.M):
            problems.append(
                f"CHANGELOG.md 里没有 v{truth} 这一节——"
                "「这一版改了什么」是出问题那天要翻的东西")

    print(f"真源 {name} 说版本是 {truth}；核了 {checked} 处")
    if problems:
        return _fail(problems)
    print("每一处声明的版本都和真源一样，CHANGELOG 里也有这一版。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
