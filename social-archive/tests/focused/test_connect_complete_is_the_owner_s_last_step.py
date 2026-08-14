"""连接账号的**最后一步**，此前一条判据都没有（v0.0.0.7 / T06）。

2026-08-05 数了一遍：api.py 里 43 条路由，判据里一次都没出现过的有 5 条，
其中一条是 `POST /v1/accounts/connect/{platform}/complete`。

**那正是 Owner 连 YouTube 时最后要走的那一步**——他在平台页面登完录，
扩展回头调这个接口把连接落库。交接里写着「他可以做的第二件事」就是它，
而它没有任何判据。

前面几步都验过了（设置页有那张卡、按钮叫「连接账号」、Cookie 白名单里有它），
唯独**点下去之后的那一下**没人验过。
"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(root / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(root / "staging"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(root / "private"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_WATCH_ROOT", str(root / "import"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app)


def _start(client: TestClient, platform: str, auth_method: str = "browser_session") -> str:
    """先走 `connect/start` 拿一个**真的** connection_ref。

    第一版直接编了一个 `conn-fixture-0001` 去调 complete，被 422 顶回来：
    「连接凭据无效，请重新连接账号」。**那是接口做对了**——它不收凭空来的 ref。
    连接本来就是两步：start（打开登录页）→ 人去登录 → complete（落库）。
    """
    started = client.post("/v1/accounts/connect/start",
                          json={"platform": platform, "auth_method": auth_method})
    assert started.status_code == 202, started.text
    ref = started.json()["connection_ref"]
    assert ref, "start 没给出 connection_ref"
    return ref


def _complete(client: TestClient, platform: str, *, connection_ref: str | None = None,
              auth_method: str = "browser_session", **overrides):
    body = {
        "connection_ref": connection_ref or _start(client, platform, auth_method),
        "external_account_id": "fixture-account",
        "display_name": "夹具账号",
        "metadata": {"auth_method": auth_method},
    }
    body.update(overrides)
    return client.post(f"/v1/accounts/connect/{platform}/complete", json=body)


def test_a_made_up_connection_ref_is_refused(tmp_path, monkeypatch):
    """**凭空来的 ref 不许收。** 否则谁都能声称「我连好了」。

    这条是上面那次失败换来的：我编了个 ref，接口 422 顶回来，
    而那正是它该做的——所以把它钉住。
    """
    client = _client(tmp_path, monkeypatch)
    response = client.post("/v1/accounts/connect/youtube/complete", json={
        "connection_ref": "conn-我随手编的",
        "external_account_id": "fixture-account",
        "display_name": "夹具账号",
        "metadata": {"auth_method": "browser_session"},
    })
    assert response.status_code == 422, response.text


def test_completing_a_youtube_connection_actually_records_it(tmp_path, monkeypatch):
    """**这就是他点完「连接账号」之后发生的那一下。**

    此前整条路只验到按钮存在为止；按下去之后落不落库，一条判据都没有。
    """
    client = _client(tmp_path, monkeypatch)
    response = _complete(client, "youtube")
    assert response.status_code == 201, response.text

    listed = client.get("/v1/accounts")
    assert listed.status_code == 200, listed.text
    platforms = [item.get("platform") for item in listed.json().get("items", [])]
    assert "youtube" in platforms, f"连接完成了，账号列表里却没有它：{platforms}"


def test_an_unknown_auth_method_is_refused(tmp_path, monkeypatch):
    """接口只认六种连接方式，别的一律 422。

    **这条不是形式主义**：auth_method 决定后面怎么取凭据，
    收下一个不认识的值，等于让一条没人实现的路悄悄进库。
    """
    client = _client(tmp_path, monkeypatch)
    response = _complete(client, "youtube", metadata={"auth_method": "telepathy"})
    assert response.status_code == 422, response.text


def test_the_six_known_methods_are_all_accepted(tmp_path, monkeypatch):
    """**反面同样要验。** 只验「拒绝非法值」的话，把允许列表整个删空也照样绿。"""
    client = _client(tmp_path, monkeypatch)
    for index, method in enumerate(
            ("oauth", "qr", "browser_session", "official_export",
             "local_import", "chrome_bookmarks")):
        response = _complete(client, "youtube", auth_method=method,
                             external_account_id=f"acct-{index}")
        assert response.status_code == 201, f"{method} 被拒了：{response.text}"


def test_reconnecting_the_same_account_does_not_double_up(tmp_path, monkeypatch):
    """「点完没反应就再点一次」是最常见的动作。

    **说准一点**：这里走的是两次完整的 start→complete，
    也就是**两个不同的 connection_ref**、同一个账号。
    （原来这条叫「同一个 ref 重复完成」，而 `_complete` 每次都会重新 start——
    描述和它实际做的事对不上。判据写错描述，比写错断言更难发现。）
    """
    client = _client(tmp_path, monkeypatch)
    first = _complete(client, "youtube")
    second = _complete(client, "youtube")
    assert first.status_code == 201 and second.status_code == 201, second.text
    items = client.get("/v1/accounts").json().get("items", [])
    youtube = [item for item in items if item.get("platform") == "youtube"]
    assert len(youtube) == 1, f"同一次连接被记成了 {len(youtube)} 个账号"


# ---- 连接流程在扩展那一侧的两颗按钮 ----
#
# 2026-08-05 又量了一次：扩展里 25 种消息类型，**判据里没出现过的 9 种**。
# 其中一种是 `SA_VERIFY_PLATFORM_SESSION`——设置页那颗「我已登录，继续」。
#
# 连接是两步：点「连接账号」打开登录页 → 人去登录 → 点「我已登录，继续」。
# **第二颗按钮此前一条判据都没有。**

from pathlib import Path  # noqa: E402

_EXT = Path(__file__).resolve().parents[2] / "apps/browser-extension"
_BACKGROUND = (_EXT / "background.js").read_text(encoding="utf-8")
_OPTIONS = (_EXT / "options.js").read_text(encoding="utf-8")


def test_both_buttons_of_the_connect_flow_have_a_listener_behind_them() -> None:
    """两颗按钮各自发的消息，后台都得真的接。

    只接第一颗的话，用户点完「我已登录，继续」什么都不会发生——
    而那正是他登录之后唯一能做的动作。
    """
    for message, button in (("SA_ACCOUNT_CONNECT", "连接账号"),
                            ("SA_VERIFY_PLATFORM_SESSION", "我已登录，继续")):
        assert message in _OPTIONS, f"设置页不再发 {message}（按钮：{button}）"
        assert f'message?.type === "{message}"' in _BACKGROUND, (
            f"后台没有接 {message}——「{button}」点下去会石沉大海"
        )


def test_the_verify_button_reaches_a_function_that_exists() -> None:
    """**真浏览器里问过**：verifyPendingPlatform 在 service worker 里是个函数。

    这条判据打在源码上，而 2026-08-05 用一次性 profile 的真 Chrome 核过一遍：
    verifyPendingPlatform / connectPlatform / captureActive /
    openAccountCenter / getPendingConnections 五个全部是函数。
    （captureActive 的 fn.length 是 0，因为它的两个参数都有默认值，不是没接上。）
    """
    assert "verifyPendingPlatform" in _BACKGROUND
    assert 'SA_VERIFY_PLATFORM_SESSION"' in _BACKGROUND
    handler = _BACKGROUND.split('message?.type === "SA_VERIFY_PLATFORM_SESSION"')[1][:120]
    assert "verifyPendingPlatform" in handler, f"这条消息没有走到那个函数：{handler[:60]}"
