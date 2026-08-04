#!/usr/bin/env python3
"""文档里引号括起来的界面词，界面上必须真有（v0.0.0.7）。

## 为什么需要它

本轮手工扫了三次，三次都找出真问题：

  1. 手册第 3 步「在连接中心授权常用平台」——那个名字 v0.0.0.6 就改成
     「账号同步中心」了。顺着这个词还牵出 `scripts/browser_acceptance.py`
     **整份对不上界面**（每个选择器 0 命中、断言已删的 XHS 通道、无人调用）。
  2. 手册第 1、2 步指着「安装浏览器插件」「连接我的档案馆」两个不存在的按钮。
  3. 「每天怎么用」教用户点「读取当前列表」——那是 **T03 整条删除**的
     DOM 抓取器的按钮，照着做只会找不到它。
     同一份文档还写卡片显示「媒体已三副本」，而真实取值只有
     完整 / 处理中 / 仅元数据。

**照着旧文档操作的人会以为是自己错了。** 这比代码里的 bug 更难被发现，
因为没有任何东西会报错。

## 判据

扫 `docs/*.md` 里 `“…”` 或 `「…」` 括起来的**短中文串**，
到 `apps/` 里找。找不到就报出来。

## 误报与豁免

- **自引用**：修文档时常要写「原文写的是"旧词"——那个已经没了」。
  这类行含有「原文/原来/已删/作废/不存在/已改」等标记，跳过。
- **散文**：引号也用来强调语气（「没看见」「命令不存在」）。
  这些进 NOT_UI_STRINGS，每条写清它不是界面词。
- 只查**存在性**，不查语境。界面上有这个词但含义变了，它查不出来。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
UI_DIRS = ("apps",)

QUOTED = re.compile(r"[“「]([^”」\n]{2,14})[”」]")
CHINESE = re.compile(r"^[一-龥A-Za-z0-9 /·]+$")

# 这一行是在说明「某个旧说法已经作废」，里面的引号是自引用，不是要求。
SELF_QUOTE_MARKERS = ("原文", "原来", "已删", "作废", "不存在", "已改", "旧词",
                      "此前", "曾经", "v0.0.0.4", "v0.0.0.5", "v0.0.0.6")

# 引号里但不是界面词的。每条写清是什么。
NOT_UI_STRINGS = {
    "降级/手动": "01_产品需求 里的策略取值，不是按钮",
    "没看见": "散文，强调语气",
    "命令不存在": "DOMESTIC_WORKERS_ZH 描述照旧文档操作会得到的报错",
    "点了同步是 0": "对 v0.0.0.6 那个症状的称呼",
    "U3 之前不扩范围": "ZERO_BARRIER_UX 的范围约定",
    "已连接": "连接状态取值，由 app.js 动态渲染，不在静态 HTML 里",
}


def ui_blob() -> str:
    chunks: list[str] = []
    for folder in UI_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix in {".js", ".html"} and path.is_file():
                try:
                    chunks.append(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    continue
    return "\n".join(chunks)


def main() -> int:
    blob = ui_blob()
    missing: list[str] = []
    scanned = 0

    for doc in sorted(DOCS.glob("*.md")):
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if any(marker in line for marker in SELF_QUOTE_MARKERS):
                continue  # 这一行是在说「旧的那个已经没了」
            for phrase in QUOTED.findall(line):
                if not CHINESE.match(phrase):
                    continue
                if not any("一" <= c <= "鿿" for c in phrase):
                    continue
                if phrase in NOT_UI_STRINGS:
                    continue
                scanned += 1
                if phrase not in blob:
                    missing.append(f"  {doc.name}:{lineno}  “{phrase}”")

    print(f"扫了 docs/ 里 {scanned} 处界面词引用")
    if missing:
        print(f"**界面上找不到的 {len(missing)} 处**——照着文档操作的人会以为是自己错了：")
        for line in missing:
            print(line)
        print("\n改文档去对齐界面，或写进 NOT_UI_STRINGS 说明它不是界面词。")
        return 1
    print("每一处都在界面上找得到。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
