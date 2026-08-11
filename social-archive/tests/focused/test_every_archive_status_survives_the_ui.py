"""服务端能发出的每一个归档状态，界面都不许改口（2026-08-10）。

## 这一处是怎么露出来的

把抽屉那一屏第一次渲染出来读（`grep -rn drawer scripts/*_drill.py` 当时是空的——
**他点开一条内容来读的那一下，从没在真浏览器里被打开过**），看到：

    归档状态 L0/L1/L3 完整 … 归档文件 · 0 项

顺着这句去读 `archiveLabel()`，发现它只认三个值：

    完整 → 「L0/L1/L3 完整」
    处理中 → 「媒体处理中」
    仅元数据 → 「L0/L1 已保存」
    其余 → **「需要处理」**

而服务端 2026-08-10 新增了第四个：**「视频没存下」**（B 站/抖音把下载挡了，
正文在、视频没有）。生产实测 **193 条里 33 条是它**，占 17%。

它落进 else，于是列表那一格（`cellHtml` 的 `case "archive"` 也调同一个函数）
和抽屉都对他说**「需要处理」**——一句听起来「你该去做点什么」的话，
而平台挡了下载，他做不了任何事。

**而说明书里白纸黑字写着**：

    那种条目正文照样存着，只是没有视频文件，资料库那一列会写「视频没存下」，
    不会假装成「完整」

承诺的那个词，产品根本不显示。`check_the_guide_matches_the_product.py`
当时是绿的——它自己写着「只保证说的每件事都存在，不检查语气」，
所以"说明书引用了一个界面不显示的词"它看不见。这条判据补的就是那个盲区。

## 病根

和 `failureSentence` 是同一个：**前端自己养一张词典，服务端加一个值它就漏一个。**
真源在服务端（那几个值本来就是给人看的中文），前端的活是**装饰已知的几个、
其余原样透传**，不是翻译。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"
DB = ROOT / "src/social_archive/db.py"
GUIDE = ROOT / "docs/使用说明.md"

pytestmark = pytest.mark.skipif(not APP.is_file(), reason="app.js 不存在")


def _server_statuses() -> set[str]:
    """服务端那条 CASE 能发出哪几个值——**从代码里取，不手抄。**

    手抄的话，服务端再加一个值这条判据就跟着漏，
    而它存在的全部理由就是拦这种漏。
    """
    sql = DB.read_text(encoding="utf-8")
    start = sql.find("AS archive_status")
    assert start > 0, "找不到 archive_status 那条 CASE——这条判据在空扫"
    window = sql[max(0, start - 2000):start]
    case_at = window.rfind("CASE")
    assert case_at >= 0, "找不到 CASE 开头"
    return set(re.findall(r"THEN\s*'([^']+)'", window[case_at:]))


def test_the_case_still_emits_more_than_one_value() -> None:
    """反空扫：一个值都没解析出来时，下面每条断言都会白过。"""
    statuses = _server_statuses()
    assert len(statuses) >= 3, f"只解析出 {statuses}——正则够不到那条 CASE 了"
    assert "视频没存下" in statuses, (
        f"服务端不再发「视频没存下」了？解析到：{statuses}——"
        "那说明书里那句承诺也该改")


def test_no_server_status_is_rewritten_into_needs_action() -> None:
    """**不许把服务端的话翻译成一句更糟的话。**"""
    code = APP.read_text(encoding="utf-8")
    start = code.find("function archiveLabel(")
    assert start >= 0, "archiveLabel 没了——这条判据在空扫"
    body = code[start:code.find("\n  function ", start + 10)]
    for status in sorted(_server_statuses()):
        decorated = re.search(rf'value === "{re.escape(status)}"', body)
        passthrough = "return value ||" in body
        assert decorated or passthrough, (
            f"服务端会发「{status}」，而 archiveLabel 既没为它写一句、也不透传——"
            f"它会落到兜底那句「需要处理」。函数体：{body[:200]}")


def test_the_guide_quote_is_a_string_the_ui_can_actually_show() -> None:
    """说明书引用了界面上的词，那个词就得真能出现。"""
    if not GUIDE.is_file():
        pytest.skip("使用说明不在")
    guide = GUIDE.read_text(encoding="utf-8")
    assert "视频没存下" in guide, "说明书里那句承诺被改了或删了"
    code = APP.read_text(encoding="utf-8")
    start = code.find("function archiveLabel(")
    body = code[start:code.find("\n  function ", start + 10)]
    assert '"视频没存下"' in body or "return value ||" in body, (
        "说明书答应「资料库那一列会写『视频没存下』」，"
        "而 archiveLabel 会把它换成「需要处理」——承诺的那个词产品不显示")
