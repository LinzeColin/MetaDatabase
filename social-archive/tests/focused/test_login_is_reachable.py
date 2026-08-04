"""产品里必须有一个能点的登录入口（v0.0.0.7 / T02）。

## 这条是被真实用户逼出来的

Owner 说「我点击也登陆了」。去生产库里查：`users` 1 行（那是 T01 迁移回填的
默认账户），**`oauth_identity` 0 行、`session` 0 行**。服务端日志里有
`GET /v1/auth/providers 200`，却没有任何一次 `/start` 或 callback。

不是他操作错了。**产品里根本没有登录按钮。**

`auth.py` 提供 7 条路由，全仓客户端只调用其中一条
（`POST /v1/auth/extension-token`）。`/v1/auth/{provider}/start` 零调用。

## 为什么一直没被发现

「接口没人调」那道门 `find_endpoints_no_client_calls.py` **只扫 api.py**，
从来没看过 `auth.py`。射程写错，本轮第六次。门已扩，这条判据是另一半：
直接钉住登录闸本身。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.focused._source_slices import js_function

ROOT = Path(__file__).resolve().parents[2]
PWA_JS = ROOT / "apps/pwa/app.js"
PWA_HTML = ROOT / "apps/pwa/index.html"
AUTH = ROOT / "src/social_archive/auth.py"


def code_only(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//") and not line.lstrip().startswith("*")
    )


def test_the_login_gate_markup_exists() -> None:
    html = PWA_HTML.read_text(encoding="utf-8")
    assert 'id="loginGate"' in html, "没有登录闸——未登录的人打开页面看不到任何入口"
    assert 'id="loginButtons"' in html


def test_the_page_asks_whether_you_are_logged_in_before_anything_else() -> None:
    """先过闸再干别的。

    否则未登录时后面每个接口都 401，用户看到的是一堆「服务连接异常」，
    而真因是没登录——把一个能自己解决的问题伪装成了服务故障。
    """
    js = code_only(PWA_JS.read_text(encoding="utf-8"))
    assert '"/v1/auth/me"' in js, "从不询问登录状态"
    body = js_function(js, "async function init")
    assert "requireLogin" in body, "init 没有先过登录闸"
    assert body.index("requireLogin") < body.index("loadUiSettings"), "登录闸不在最前面"


def test_every_configured_provider_gets_a_button_and_the_click_goes_somewhere() -> None:
    js = code_only(PWA_JS.read_text(encoding="utf-8"))
    assert '"/v1/auth/providers"' in js, "不问服务端支持哪些登录方式"
    assert "item.configured" in js, "没过滤掉没配好的 provider——会画出点了就 503 的按钮"
    assert re.search(r"data-login-provider", js), "没有画出登录按钮"
    assert re.search(r'/v1/auth/\$\{encodeURIComponent\(provider\)\}/start', js), "按钮没有真的去发起登录"
    # **必须是顶层跳转，且必须跳到 login_base 那个域。**
    #
    # state cookie 是 host-only：在哪个域调 /start 就种在哪个域，而回调地址
    # 固定是 login_base。两者不同域 → 回调收不到 state → 400「登录链接已失效」。
    # 实测：Owner 在资料库域点了好几次，callback 全是 400、session 始终 0。
    #
    # 用 fetch 也不行——跨域 fetch 种不上 SameSite=lax 的 cookie。
    assert "state.loginBase" in js, "没有按 login_base 决定去哪个域发起登录"
    assert "login_base" in js, "不读服务端给的 login_base"
    assert re.search(r'location\.href = `\$\{base\}/v1/auth/', js), "登录不是顶层跳转"
    assert "redirect=1" in js, "没有用 302 模式——fetch 拿到 JSON 之后跨域种不上 state cookie"


def test_login_can_be_undone() -> None:
    """INV-REVERSIBLE：能登进来就要能退出去，能发令牌就要能收回来。"""
    js = code_only(PWA_JS.read_text(encoding="utf-8"))
    assert '"/v1/auth/logout"' in js, "没有退出登录"
    assert "settingLogout" in js
    assert re.search(r'"/v1/auth/extension-token",\s*\{\s*method:\s*"DELETE"', js), (
        "扩展令牌发得出去、收不回来"
    )


def test_the_endpoint_gate_now_covers_the_auth_router() -> None:
    """守住发现方式本身：门只扫 api.py 的话，这一切还会再发生一次。"""
    gate = (ROOT / "scripts/find_endpoints_no_client_calls.py").read_text(encoding="utf-8")
    assert "auth.py" in gate, "接口门又只扫 api.py 了"
    assert AUTH.is_file()


def test_the_callback_uses_the_domain_that_is_actually_registered() -> None:
    """回调地址必须与 login_base、登录后落点是**同一个域**。

    实测（2026-08-04）：Google 对 `public_base_url`（API 域）那个回调地址
    明确回 **Error 400: redirect_uri_mismatch**，对 `public_library_url`
    那个则认。Owner 当初登记的是资料库域，代码却一直在用 API 域。

    三处必须一致，任何一处漂开都会重新制造那个 400：

      _redirect_uri   → 决定 Google 把人送回哪
      login_base      → 决定界面在哪个域发起登录（state cookie 种在那里）
      登录后的落点     → 会话 cookie 在哪个域，就必须跳回哪个域

    **不要靠「跳到了登录页」推断地址已登记**——那一跳是无条件的，
    Google 在其后才校验。本轮就是这么先下错了一次结论。
    """
    text = (ROOT / "src/social_archive/auth.py").read_text(encoding="utf-8")
    redirect_fn = text.split("def _redirect_uri", 1)[1].split("\ndef ", 1)[0]
    assert "public_library_url" in redirect_fn, "回调地址又用回了没登记的那个域"
    assert '"login_base": settings.public_library_url' in text, "login_base 与回调地址不同域"
    assert 'RedirectResponse(f"{settings.public_library_url' in text, "登录后跳去了会话 cookie 不在的域"
