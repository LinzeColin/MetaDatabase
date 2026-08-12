r"""「下载全部 Markdown」点不出东西时，那句话要指得出真按钮（2026-08-10）。

## 从哪来

在真制品上走了一遍全新实例：点下载 → 503，回的是

    还没有生成过 Markdown——先让「Markdown」那个导出目的地跑一次

照着做会撞第二堵墙：`/v1/destinations/markdown/backfill` 回
「这个目的地还没有一次成功的写入授权，先在连接向导里完成一次真实写入」。
**指了一个走不通的出口** —— 这个仓专门为这个形状记过一条教训。

界面上真实的顺序是：「自动导出」栏 → Markdown 卡片 → 点「检查连接」
→ 连上之后才会出现「把没送过去的 N 条补上」（`backfillButton` 里
`item.state !== "connected"` 就不渲染）。

## 钉什么

那句话里点名的每一个界面文字，都必须在界面文件里真的存在。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
APP_JS = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")

MESSAGE = next((line for line in API.splitlines() if "还没有生成过 Markdown" in line), "")
QUOTED = re.findall(r"「([^」]+)」", MESSAGE)


def test_the_message_exists_and_names_something() -> None:
    """反空扫：那句话没了、或者一个按钮都没点名，下面就会白过。"""
    assert MESSAGE, "找不到「还没有生成过 Markdown」那句话——判据在空扫"
    assert len(QUOTED) >= 2, f"那句话只点名了 {QUOTED}——空态必须指得出具体点哪儿"


@pytest.mark.parametrize("label", QUOTED or ["(空)"])
def test_every_label_it_names_is_really_on_screen(label: str) -> None:
    # 「把没送过去的 N 条补上」里的 N 是变量，只比固定的那截
    needle = label.split(" N ")[0] if " N " in label else label
    assert needle in APP_JS or needle in INDEX, (
        f"空态那句话让他点「{label}」，而界面文件里没有这几个字——"
        "他照着找会找不到，只能回来问我")


def test_it_does_not_send_him_to_a_wall() -> None:
    """**顺序要对**：先「检查连接」，连上之后才会出现「补上」那颗。

    直接让他点「补上」的话，全新实例上那颗按钮**根本不渲染**
    （`backfillButton`: `item.state !== "connected"` 就返回空串）。
    """
    assert 'item.state !== "connected"' in APP_JS, (
        "backfillButton 的渲染条件变了——这条判据钉的顺序可能已经不对，先去看界面")
    order = MESSAGE.index("检查连接") < MESSAGE.index("把没送过去的")
    assert order, "那句话把「补上」写在了「检查连接」前面——照着做会点不到"
