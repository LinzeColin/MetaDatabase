#!/usr/bin/env python3
r"""把桌面上那两个双击文件刷新成仓里这一份（含当前的生产主机名）。

## 为什么需要它

Owner 双击的是 `~/Desktop/同步到 Obsidian.command`。那个文件**必须自包含**
——它不能依赖 `deploy/PRODUCTION_HOST`，因为 `_scratch/` 里的工作树随时会被回收
（今天已经有一棵在部署跑到一半时整棵消失过）。

自包含的代价是：主机名在里面是**字面值**。所以换机器时它不会自动跟上。
这个脚本就是那一步——`deploy/PRODUCTION_HOST` 改完，跑一次这个。

不跑的话：改完真源、部署也切了，而他一双击还是连旧机器，
**而且什么都不会报错**。

## 它做什么

  · 把 `scripts/同步到 Obsidian.command` 复制到桌面，并把里面的
    `HOST="${SOCIAL_ARCHIVE_HOST:-<旧名>}"` 换成当前真源
  · 顺带保证「只补收藏」那个包装文件在（它只是 exec 前一个，零逻辑）
  · `--check` 只比对不落盘：桌面那份和仓里这份（按当前真源展开后）是否一致
"""

from __future__ import annotations

import argparse
import re
import shutil
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_host import deploy_host  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/同步到 Obsidian.command"
DESKTOP = Path.home() / "Desktop"
MAIN = DESKTOP / "同步到 Obsidian.command"
FAVOURITES = DESKTOP / "只补收藏到 Obsidian.command"

FAVOURITES_BODY = '''#!/bin/bash
# 双击这个：只把「收藏」补进 Obsidian，不带点赞、不带观看历史。
#
# **它只管少放东西进来，不会把库里已经有的清掉。**
# 你库里现在已经有的点赞/历史笔记还在原地 —— rsync 只加不删，
# 我不会替你删你库里的文件。要清掉它们的话跟我说，我给你一份清单再动手。
#
# 旁边那个「同步到 Obsidian.command」是全部内容（收藏 + 点赞 + 历史 + …）。
# 两个都可以反复双击，跑完都会把库里的标题修好、去重，结果一样收敛。

exec env SOCIAL_ARCHIVE_ONLY_RELATION=favorite \\
  /bin/bash "$HOME/Desktop/同步到 Obsidian.command" "$@"
'''

HOST_LINE = re.compile(r'^HOST="\$\{SOCIAL_ARCHIVE_HOST:-[^}]*\}"$', re.M)


def rendered() -> str:
    """仓里那一份，主机名换成当前真源。"""
    text = SOURCE.read_text(encoding="utf-8")
    wanted = f'HOST="${{SOCIAL_ARCHIVE_HOST:-{deploy_host()}}}"'
    new, count = HOST_LINE.subn(wanted, text, count=1)
    if count != 1:
        raise SystemExit(
            f"在 {SOURCE.name} 里找不到那一行 HOST=…——"
            "**结构变了就别猜着替换**，先看一眼再改这个脚本。")
    return new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只比对，不落盘")
    args = parser.parse_args()

    wanted = rendered()
    problems: list[str] = []
    if not MAIN.is_file():
        problems.append(f"桌面上没有 {MAIN.name}")
    elif MAIN.read_text(encoding="utf-8") != wanted:
        problems.append(f"{MAIN.name} 和仓里这份不一致（主机名或内容漂了）")
    if not FAVOURITES.is_file():
        problems.append(f"桌面上没有 {FAVOURITES.name}")

    if args.check:
        if problems:
            print("  " + "\n  ".join(problems))
            print(f"  跑 `python3 {Path(__file__).relative_to(ROOT)}` 刷新")
            return 1
        print(f"  桌面那两个文件都是最新的（生产主机 {deploy_host()}）。")
        return 0

    MAIN.write_text(wanted, encoding="utf-8")
    MAIN.chmod(MAIN.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    FAVOURITES.write_text(FAVOURITES_BODY, encoding="utf-8")
    FAVOURITES.chmod(FAVOURITES.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  已刷新桌面两个文件；生产主机 = {deploy_host()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
