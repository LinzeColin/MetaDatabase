"""从源码里切出「要看的那一段」——**按结构切，不按字节数切**。

判据经常要读一段 JS 源码然后断言它里面有什么。切法有三种，两种是错的：

  · `[:5000]` 固定窗口 —— 2026-08-05 实测：给 runDiagnosis 加了几行注释，
    就把 /v1/extension/diagnostics 挤出了某条判据的窗口，判据当场变红，
    **而代码一点没坏**。
  · 锚在注释上 —— 本会话已经因此误报过一次（注释里提到某个函数名，
    判据以为找到了那个函数）。

两种都是同一族毛病：**钉的是位置，不是事实。**
这里统一按函数边界切，并且切不到就直接报错，不许静默退化成空串。
"""

from __future__ import annotations


def js_function_body(source: str, declaration: str, *boundaries: str) -> str:
    """从 `declaration` 切到下一个同级声明（或文件末尾）。

    切不到 `declaration` 时**抛断言错误**——一个悄悄返回空串的切片，
    会让后面每一条 `assert x in body` 都变成假绿。
    """
    assert declaration in source, f"源码里找不到 {declaration}——判据钉的东西没了"
    body = source.split(declaration, 1)[1]
    for boundary in boundaries:
        if boundary in body:
            body = body.split(boundary, 1)[0]
    return body


def run_diagnosis_body(popup_js: str) -> str:
    """popup.js 里 runDiagnosis 的整个函数体。"""
    return js_function_body(
        popup_js, "async function runDiagnosis", "\n  async function ", "\n  function "
    )


def install_net_observer_body(background_js: str) -> str:
    """background.js 里 installNetObserverForTab 的整个函数体。

    这段代码 2026-08-05 从消息处理器里整段挪了出来，只为一件事：
    让真浏览器演练能调它本人，而不是照抄一遍它的顺序。
    """
    return js_function_body(
        background_js, "async function installNetObserverForTab", "\nasync function"
    )
