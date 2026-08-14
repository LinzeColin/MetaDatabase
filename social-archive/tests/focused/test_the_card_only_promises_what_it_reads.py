"""设置页那张卡不许承诺这一版不会读的东西（v0.0.0.13）。

2026-08-06 在真 Chrome 里第一次看那张卡，读回来的原文是：

    B站  未连接  收藏夹、稍后再看、历史、点赞  [连接账号]

而这一版**只读收藏夹**。他点「连接账号」时以为四样都会同步，连上之后
只会看到一样——这和验收标准里那句「绝不给一颗结构上不可能成功的按钮」
是同一类问题：按钮能按，但它承诺的东西有四分之三不会发生。

根因是 `options.js` 的 `relationCopy` 是一张**写死的散文表**。散文最危险：
它不是逐项列举，改了扫描范围也不会有人想起去改它。
现在改成照 `SCANNABLE_RELATIONS` 现算。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "apps/browser-extension/content/platform-catalog.js"
OPTIONS_JS = ROOT / "apps/browser-extension/options.js"
OPTIONS_HTML = ROOT / "apps/browser-extension/options.html"


def _node(expression: str) -> str:
    script = (f'const c = require("{CATALOG}");\n'
              f'console.log(JSON.stringify({expression}));')
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-400:]
    return json.loads(done.stdout.strip())


def test_the_summary_lists_exactly_what_gets_scanned() -> None:
    from social_archive.account_sync import PLATFORM_RELATIONS

    summary = _node('c.scannableSummary("bilibili")')
    assert summary == "收藏夹", f"B 站那张卡会写「{summary}」，而这一版只读收藏夹"
    # 平台目录里 B 站声明了四种关系——**卡片不许照它写**
    assert len(PLATFORM_RELATIONS["bilibili"]) > 1, "前提变了：B 站不再声明多种关系"
    for word in ("稍后再看", "观看历史", "点赞"):
        assert word not in summary, f"卡片承诺了这一版不会读的「{word}」"


def test_the_options_page_can_actually_reach_the_catalog() -> None:
    """**光改 options.js 不够，页面得真的加载得到那份目录。**

    这个项目栽过一次一模一样的：CONNECT_IS_CLICKABLE_TODAY 里写了很详细的
    一句话，而没有任何界面读那个字段——写完就是隐形的。
    """
    html = OPTIONS_HTML.read_text(encoding="utf-8")
    assert "content/platform-catalog.js" in html, (
        "options.html 没有加载平台目录——options.js 里那次调用永远拿不到它，"
        "只会一路退回写死的散文表"
    )
    # 顺序也要对：目录必须在 options.js 之前
    assert html.index("content/platform-catalog.js") < html.index("options.js"), (
        "平台目录得排在 options.js 前面，否则用到的时候它还不存在"
    )


def test_options_js_prefers_the_catalog_over_the_hardcoded_prose() -> None:
    code = "\n".join(line for line in OPTIONS_JS.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    assert "scannableSummary" in code, "设置页没有照实际扫描范围写那句话"
    # relationCopy 仍然保留：取数路还没做的平台用它，行为不变
    assert "relationCopy" in code, "没登记扫描范围的平台还要靠它，别一起删了"


def test_every_registered_platform_promises_a_subset_of_what_it_scans() -> None:
    """登记过扫描范围的平台，那句话必须**恰好**是扫描范围，不多不少。"""
    registered = _node("Object.keys(c.SCANNABLE_RELATIONS)")
    assert registered, "一个都没登记——这条判据就成了摆设"
    for platform in registered:
        scanned = _node(f'c.scannableRelations({platform!r})')
        summary = _node(f'c.scannableSummary({platform!r})')
        labels = [_node(f'c.relationLabel({r!r})') for r in scanned]
        assert summary == "、".join(labels), (
            f"{platform} 卡片上写「{summary}」，而实际扫描的是 {labels}"
        )
