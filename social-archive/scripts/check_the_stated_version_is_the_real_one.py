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
    # 下面四处是 2026-08-06 / G5 补的。它们**一直是承重位，只是这道门看不见**：
    # 升版时全靠手改，而这台机器已经因为手改版本位出过两次错（两次都是漏了位）。
    ("VERSION", re.compile(r"^\s*([0-9.]+)\s*$"),
     "**部署脚本拿它拼镜像 tag**（social-archive/core:${VERSION}）。"
     "它和 compose.yaml 里 pin 的 tag 一旦不一致，"
     "部署起来的就不是刚构建的那个镜像——而且现场看不出来"),
    ("apps/browser-extension/runtime-config.json", None,
     "插件界面上显示的版本；和 manifest 不一致会让人以为装错了"),
    ("compose.yaml", re.compile(r"image:\s*social-archive/core:([0-9.]+)"),
     "生产真正跑的那个镜像 tag"),
    ("compose.yaml", re.compile(r"image:\s*social-archive/cli-tools:([0-9.]+)"),
     "sidecar 镜像 tag"),
    # 这一处是升版当天被一条测试撞出来的——**而它是最贵的一处**：
    # 资料库页面用它判插件兼容性（`compatible: version === PRODUCT_VERSION`）。
    # 它不跟着升，资料库会把刚更新好的插件判成不兼容，Owner 就又回到
    # 「去更新 → 更新完还是去更新」那个循环里——正是这一轮开工时要修的那件事。
    ("apps/pwa/app.js", re.compile(r'const PRODUCT_VERSION = "([0-9.]+)"'),
     "**资料库页面判断插件兼容性的那个数**"),
    ("apps/obsidian-plugin/manifest.json", None,
     "Obsidian 插件报的版本"),
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
        text = changelog.read_text(encoding="utf-8")
        if not re.search(rf"^##\s+v{re.escape(truth)}\b", text, re.M):
            problems.append(
                f"CHANGELOG.md 里没有 v{truth} 这一节——"
                "「这一版改了什么」是出问题那天要翻的东西")
        # **反过来那一半：CHANGELOG 宣布了一个代码里不存在的版本。**
        #
        # 2026-08-06 我就这么干了一次：`bump_version.py 0.0.0.22` 少给了
        # `--apply`（不给就只看），报告里的 `"applied": false` 我没读，
        # 于是**版本号一处都没改**，而 CHANGELOG 已经写好了 v0.0.0.22 那一节。
        # 接着提交、部署、验收——全绿。生产上跑的是 0.0.0.21 的镜像，
        # 而仓里躺着一份宣布 0.0.0.22 已经发布的变更记录。
        #
        # 原来的判据只问「当前版本有没有条目」，**方向是单向的**：
        # 记录跑到代码前面去，它一个字都不会说。
        newest = max((tuple(int(part) for part in found.split("."))
                      for found in re.findall(r"^##\s+v(\d+(?:\.\d+){1,3})\b", text, re.M)),
                     default=None)
        if newest and newest > tuple(int(part) for part in truth.split(".")):
            stated_newest = ".".join(str(part) for part in newest)
            problems.append(
                f"CHANGELOG.md 最新一节是 v{stated_newest}，而真源 {name} 说版本是 "
                f"v{truth}——**变更记录跑到代码前面去了**。"
                "多半是升版工具只跑了预览没跑 --apply：那份记录在宣布一件没发生的事")

    print(f"真源 {name} 说版本是 {truth}；核了 {checked} 处")
    if problems:
        return _fail(problems)
    print("每一处声明的版本都和真源一样，CHANGELOG 里也有这一版。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
