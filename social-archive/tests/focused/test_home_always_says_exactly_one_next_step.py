"""首页永远只告诉用户一件事（v0.0.0.7 / INV-ZERO-BARRIER）。

## Owner 的原话

> 「非常不好用 而且你的流程逻辑非常混乱 我都不知道应该怎么操作」
> 「然后我就一步步去连接软件」

首页此前把同步状态、账号表、导出、设置一起摊开，**没有任何一处说"现在该干嘛"**。
用户要自己从一屏信息里推断下一步——那正是零门槛要消灭的东西。

## 规则

按顺序找到**第一个**没做完的事，只显示它；全做完就什么都不显示。
不排优先级、不并列、不给第二个选项——**多给一个选择就是多一次犹豫**。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"
HTML = ROOT / "apps/pwa/index.html"


def code_only(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//") and not line.lstrip().startswith("*")
    )


def block() -> str:
    js = code_only(APP.read_text(encoding="utf-8"))
    body = js.split("function renderNextStep", 1)[1]
    nxt = re.search(r"\n  (?:async )?function ", body)
    return body[: nxt.start()] if nxt else body


def test_the_home_page_has_a_next_step_slot() -> None:
    html = HTML.read_text(encoding="utf-8")
    for node in ("nextStep", "nextStepTitle", "nextStepWhy", "nextStepAction"):
        assert f'id="{node}"' in html, f"缺少 {node}"


def test_it_shows_exactly_one_step_at_a_time() -> None:
    """`find` 而不是 `filter`：只取第一个未完成项。"""
    text = block()
    assert re.search(r"steps\.find\(", text), "没有「只取第一个」的语义——可能会同时显示多条"
    assert "classList.add(\"hidden\")" in text, "全做完时不会把它藏起来"


def test_every_step_says_why_and_gives_one_button() -> None:
    """只说「去做 X」不够，得说为什么——否则用户不知道自己在干嘛。"""
    text = block()
    steps = re.findall(r"title:\s*[\"`]", text) + re.findall(r"title:\s*`", text)
    assert len(steps) >= 4, f"步骤太少，覆盖不了首次流程：{len(steps)}"
    assert text.count("why:") == len(steps), "有步骤没有写「为什么」"
    assert text.count("action:") == len(steps), "有步骤没有按钮文字"
    assert text.count("run:") == len(steps), "有步骤按钮点了没反应"


def test_the_first_step_is_installing_the_extension() -> None:
    """没有插件时，别的什么都做不了——它必须排第一。"""
    text = block()
    first = text.index("need:")
    assert "state.extension.detected" in text[first:first + 200], "第一步不是判断插件在不在"


def test_it_does_not_push_people_toward_platforms_that_cannot_sync() -> None:
    """「连接一个来源」这一步必须只算能同步的，否则又是一次白忙。"""
    text = block()
    assert "sync_supported" in text, "没有区分能不能同步"
    # **这一条原来断言那句话里要出现「小红书」和「暂时还不能」。**
    #
    # 它守的是「别把人推向做不到的平台」——那个用意对，保留。
    # 但它是靠**一句硬编码的文案**来守的，而那句文案 2026-08-05 实测
    # 已经过期了：它写着「Chrome 书签，以及连接后的 X / Instagram」，
    # 而 X 与 Instagram 都已经进了 NOT_SYNCABLE_YET。
    # **判据盯着一句会过期的话，就会跟着一起过期。**
    #
    # 现在那句话从 state.platformSupport 现算，所以改成钉住机制：
    # 既要按能力筛选，那句说明也不许再硬编码平台名单。
    assert "state.platformSupport" in text, "那句说明不是从能力声明现算的"
    for hardcoded in ("X / Instagram", "小红书、抖音、B站、快手"):
        assert hardcoded not in text, f"又硬编码了平台名单：{hardcoded}"


def test_it_is_recomputed_after_anything_changes() -> None:
    js = code_only(APP.read_text(encoding="utf-8"))
    assert js.count("renderNextStep()") >= 2, "只算一次的话，做完一步之后它不会更新"
