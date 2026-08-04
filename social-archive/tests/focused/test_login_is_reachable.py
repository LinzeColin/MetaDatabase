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
    body = js.split("async function init()", 1)[1][:400]
    assert "requireLogin" in body, "init 没有先过登录闸"
    assert body.index("requireLogin") < body.index("loadUiSettings"), "登录闸不在最前面"


def test_every_configured_provider_gets_a_button_and_the_click_goes_somewhere() -> None:
    js = code_only(PWA_JS.read_text(encoding="utf-8"))
    assert '"/v1/auth/providers"' in js, "不问服务端支持哪些登录方式"
    assert "item.configured" in js, "没过滤掉没配好的 provider——会画出点了就 503 的按钮"
    assert re.search(r"data-login-provider", js), "没有画出登录按钮"
    assert re.search(r'/v1/auth/\$\{encodeURIComponent\(provider\)\}/start', js), "按钮没有真的去发起登录"
    # start 只回 authorize_url，**跳转要客户端自己做**；不跳等于点了没反应
    assert "location.href = url" in js, "拿到授权地址却没跳过去"


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
