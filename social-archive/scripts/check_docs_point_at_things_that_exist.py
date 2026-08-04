#!/usr/bin/env python3
"""文档让人跑的东西，必须真的存在（v0.0.0.7 / T18）。

## 为什么

文档里最要命的一句，是**出事那天才会被人读到的那一句**。运维手册第 14 行写着

    bash scripts/restore.sh --dry-run <恢复点>

那一天再发现这个脚本不在，是最坏的时机——而且那时候没人有心情去翻仓库。

这道门只做一件很小的事：把文档里出现的 `scripts/xxx` 逐个去磁盘上找一下。

## 已知且**故意**指向不存在文件的地方

`docs/DOMESTIC_WORKERS_ZH.md` 开头写着「不要照着这份文档的旧内容操作」，
然后**特意点名**那两个已删除的脚本，好让照着旧版做的人知道发生了什么。
那是对的，所以它在白名单里——但白名单只对**明确标了作废的文档**开口。

## 边界

· 只查 `scripts/` 开头的路径。文档里还有别的路径，但那一类没人会照着敲。
· 只查存在，不查内容对不对——那是另一件事，也更难自动化。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# --root 让判据能在一份**临时副本**上验这个检查器，而不必去改仓里的真文档。
# 一个会写仓里文件的判据是不可重入的：跑到一半被打断，就把一个改坏的文档
# 留在工作树里；两次同时跑还会互相踩。
_ARGUMENT_ROOT = None
if "--root" in sys.argv:
    _position = sys.argv.index("--root")
    if _position + 1 < len(sys.argv):
        _ARGUMENT_ROOT = sys.argv[_position + 1]

ROOT = Path(_ARGUMENT_ROOT).resolve() if _ARGUMENT_ROOT else Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# 明确标了作废、且**目的就是点名已删除脚本**的文档。
# 加进这张表之前先问一句：这份文档开头有没有一句让人别照着做的话？
DELIBERATELY_POINTS_AT_DELETED = {
    "DOMESTIC_WORKERS_ZH.md": "开头已声明「不要照着这份文档的旧内容操作」，正文点名两个已删除的脚本是为了让人知道发生了什么",
}

SCRIPT_REFERENCE = re.compile(r"scripts/[A-Za-z0-9_.-]+")


def main() -> int:
    if not DOCS.is_dir():
        print("docs/ 不在，跳过——**这不是通过**。")
        return 0

    missing: list[str] = []
    checked = 0
    for document in sorted(DOCS.rglob("*.md")):
        name = document.name
        text = document.read_text(encoding="utf-8")
        for reference in sorted(set(SCRIPT_REFERENCE.findall(text))):
            checked += 1
            if (ROOT / reference).exists():
                continue
            if name in DELIBERATELY_POINTS_AT_DELETED:
                continue
            missing.append(f"{document.relative_to(ROOT)} 让人跑 {reference}，而它不在")

    print(f"扫了 docs/ 下 {len(list(DOCS.rglob('*.md')))} 份文档，"
          f"{checked} 处 scripts/ 引用；另有 {len(DELIBERATELY_POINTS_AT_DELETED)} 份已登记为「故意指向已删除的」")
    if missing:
        print(f"**不合格 {len(missing)} 处**：")
        for item in missing:
            print(f"  {item}")
        print("  ↳ 文档里最要命的一句，是出事那天才会被人读到的那一句。")
        return 1
    print("文档让人跑的每一个脚本都在。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
