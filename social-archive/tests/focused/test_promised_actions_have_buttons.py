"""产品许诺的动作，界面上必须真有那颗按钮（v0.0.0.7 / T06 · T14）。

## 这一条是怎么发现的

不是审代码审出来的，是新加的一道门 `find_messages_with_only_one_end.py`
第一次跑就报出来的：`SA_REVOKE_PLATFORM_SESSION` **有人听、没人发**。

顺着那条消息往回看，发现的是一句假话：

    background.js 连接成功时返回
      「已连接，登录状态已加密保存（N 条）。**随时可以一键撤销。**」
    api.py PUT /v1/credentials 返回
      「登录信息已加密保存，**随时可以一键撤销**。」

而「撤销」这件事当时只存在于两处代码里——服务端的 DELETE 路由，
以及扩展里那个没人调用的处理体。**没有任何界面能发出那条消息。**

同一次扫描还发现 `POST /v1/destinations/receipts/{id}/retry` 全仓唯一的
调用方是验收脚本 `browser_acceptance.py`：能被测试驱动，用户点不到。
而冻结词典里好几句文案都以「[ 重试 ]」收尾。

## 为什么打在源码文本上

这两件事的缺陷形态就是「代码齐全但两头没接上」。判据必须看的是**接没接上**，
而不是某个函数被调用时的行为——后者在缺陷存在时照样能过（处理体本来就是好的）。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.focused._source_slices import js_function

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"
PWA = ROOT / "apps/pwa/app.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """剥掉注释。本轮被自己写的说明文字骗过三次。"""
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//") and not line.lstrip().startswith("*")
    )


def test_revoke_is_promised_in_words() -> None:
    """先确认那句承诺确实在产品里说了——否则下面几条就没有前提。"""
    background = read(EXT / "background.js")
    api = read(ROOT / "src/social_archive/api.py")
    assert "随时可以一键撤销" in background
    assert "随时可以一键撤销" in api


def test_some_ui_actually_sends_the_revoke_message() -> None:
    """有界面发得出 SA_REVOKE_PLATFORM_SESSION。**这是那句承诺的真假所在。**"""
    senders = [
        path.name for path in sorted(EXT.rglob("*.js"))
        if path.name != "background.js"
        and "SA_REVOKE_PLATFORM_SESSION" in code_only(read(path))
    ]
    assert senders, (
        "没有任何界面能发出撤销消息——「随时可以一键撤销」在产品上是假的。"
        "服务端 DELETE 路由和扩展处理体都在，只差没人按得到。"
    )


def test_the_revoke_button_is_rendered_where_the_platform_is_listed() -> None:
    """按钮要出现在卡片里，而不只是存在一个函数。"""
    options = code_only(read(EXT / "options.js"))
    # **不能只断言属性名出现过。** 第一版就是这么写的，结果把整段按钮 HTML
    # 摘掉之后判据照样全绿——因为 querySelectorAll("[data-revoke-platform]")
    # 这一行里也有那个字符串。判据被自己要找的选择器满足了。
    assert re.search(r"<button[^>]*data-revoke-platform", options), (
        "撤销按钮没有被渲染出来（只有绑定、没有按钮）"
    )
    assert 'querySelectorAll("[data-revoke-platform]")' in options, (
        "按钮画出来了但没绑点击——这正是「看着接上了」"
    )


def test_revoke_goes_through_background_so_permissions_come_back_too() -> None:
    """撤销不能只删服务端。

    库里删了而浏览器权限还留着，用户在扩展详情页看到的仍是
    「这个插件能读我的 Cookie」——撤销了却看不出撤销了。
    权限 API 只有 background 能调，所以界面必须走消息而不是直接 fetch。
    """
    options = code_only(read(EXT / "options.js"))
    background = read(EXT / "background.js")
    # **切的是真正那个函数，不是「第一次出现 revokePlatform 之后的 600 字」。**
    #
    # 原来那样写是个**假绿**：options.js 里 revokePlatform 出现三次，
    # 头两次都在第 165 行那句事件绑定里（调用 + button.dataset.revokePlatform），
    # 而函数定义在第 205 行。split(..., 1) 静默取第一处，600 字的窗口
    # 根本够不到函数体——2026-08-05 实测：往真正的 revokePlatform 里塞一句
    # `fetch("/v1/credentials/x",{method:"DELETE"})`，**这条判据照样通过**。
    revoke = js_function(options, "async function revokePlatform")
    assert "/v1/credentials" not in revoke, (
        "撤销绕过 background 直接调了 DELETE——那样浏览器这边的 cookies 权限不会被交还"
    )
    revoke_block = background.split('"SA_REVOKE_PLATFORM_SESSION"', 1)[1][:900]
    assert "permissions.remove" in revoke_block


def test_the_options_page_can_tell_a_credential_is_stored() -> None:
    """走 Cookie 托管连接**不会**建 source_account 行。

    此前这一页只看 accounts，于是连接成功弹出「已连接（N 条）」之后，
    刷新回来卡片仍然显示「未连接」——用户看到的是连接失败了。
    """
    options = code_only(read(EXT / "options.js"))
    assert '"/v1/credentials"' in options, "这一页从不问服务端哪些平台存着登录状态"
    assert "credentials.find" in options or "credentials.some" in options


def test_failed_destination_receipts_can_be_retried_from_the_ui() -> None:
    """冻结词典里的「[ 重试 ]」得对应一颗真按钮。"""
    pwa = code_only(read(PWA))
    # 同上：断言的是**按钮本身**，不是属性名在文件里出现过。
    assert re.search(r"<button[^>]*data-retry-receipt", pwa), (
        "失败的目的地回执在界面上没有任何补救动作（只有绑定、没有按钮）"
    )
    assert re.search(
        r'/v1/destinations/receipts/\$\{[^}]+\}/retry`,\s*\{\s*method:\s*"POST"',
        pwa,
    ), "重试按钮没有真的去调那个接口"
    assert 'querySelectorAll("[data-retry-receipt]")' in pwa


def test_retry_button_only_appears_on_failed_receipts() -> None:
    """服务端对非 failed 的回执返回 409。

    界面上就该是「根本没有这颗按钮」，而不是点了才被拒绝——
    点了才知道不能点，是把服务端的校验当成了交互设计。
    """
    pwa = code_only(read(PWA))
    block = js_function(pwa, "function renderReceiptList")
    assert 'status === "failed"' in block, "所有回执都画了重试按钮，非失败的点下去会 409"


def test_the_acceptance_script_does_not_count_as_a_client() -> None:
    """验收脚本能驱动的东西，用户点不到。

    这条判据守的是发现方式本身：`browser_acceptance.py` 里有对
    `/v1/jobs/{id}/retry` 的 POST 处理，正因为它被算成「有人调」，
    这个缺口才一直没暴露。射程写错过三次，这次写成判据。
    """
    gate = read(ROOT / "scripts/find_messages_with_only_one_end.py")
    assert 'APPS = ROOT / "apps"' in gate
    assert "scripts" not in gate.split("APPS = ROOT", 1)[1].split("\n", 1)[0]
