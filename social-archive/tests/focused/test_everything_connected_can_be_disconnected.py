"""加了什么就要能撤什么（v0.0.0.7 / INV-REVERSIBLE）。

## 怎么发现的

清点每条不变量各有几个机器守卫，INV-REVERSIBLE 只有一个（回滚脚本）。
把路由表按「正向动作 ↔ 反向动作」比一遍：

    POST /extension-token            ↔  DELETE /extension-token         ✓
    PUT  /v1/credentials/{platform}  ↔  DELETE /v1/credentials/{…}      ✓
    登录                              ↔  登出                            ✓
    **POST /v1/accounts/connect/…    ↔  （什么都没有）**

连一个账号是一次点击，断开做不到。而连上之后它每 6 小时自己跑一次
（auto_sync_enabled + sync_interval_minutes 默认 360），
**用户没有任何办法让它停下来。**

## 断开只断连接，不删内容

归档的意义就是东西留下来。断开是"别再替我去取了"，不是"把我存的东西清掉"。
这条判据把这个界线钉死：内容数在断开前后必须一模一样。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.focused._source_slices import py_function

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "src/social_archive/api.py"
AUTH = ROOT / "src/social_archive/auth.py"

ROUTE = re.compile(r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*"([^"]+)"')


def routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in (API, AUTH):
        for method, route in ROUTE.findall(path.read_text(encoding="utf-8")):
            found.add((method.upper(), route))
    return found


def test_every_reversible_pair_has_both_halves() -> None:
    """正反成对的三处必须都在。少了反的那一半就是加得了撤不掉。"""
    have = routes()
    pairs = [
        (("POST", "/extension-token"), ("DELETE", "/extension-token")),
        (("PUT", "/v1/credentials/{platform}"), ("DELETE", "/v1/credentials/{platform}")),
    ]
    for forward, backward in pairs:
        assert forward in have, f"正向动作不见了：{forward}"
        assert backward in have, f"**加得了撤不掉**：有 {forward} 却没有 {backward}"


def test_connecting_an_account_can_be_undone() -> None:
    """本轮补上的那一半。"""
    have = routes()
    assert ("POST", "/v1/accounts/connect/start") in have
    assert ("DELETE", "/v1/accounts/{account_id}") in have, (
        "能连账号却不能断开——连上之后每 6 小时自己跑一次，用户没办法让它停"
    )


def test_disconnect_stops_auto_sync_and_keeps_the_content(tmp_path) -> None:
    """行为判据：不再自动同步、在跑的落到 cancelled、**内容一条不少**。"""
    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    account_id = store.upsert_source_account(
        platform="reddit", external_account_id="spez", display_name="Reddit",
        auth_method="browser_session", auth_handle_ref=None,
        connection_state="connected", auto_sync_enabled=True,
    )
    before = {a["id"]: a for a in store.list_source_accounts()}[account_id]
    assert before["auto_sync_enabled"] is True

    result = store.disconnect_source_account(account_id)
    assert result["found"] is True
    assert result["already_disconnected"] is False

    after = {a["id"]: a for a in store.list_source_accounts()}[account_id]
    assert after["connection_state"] == "disconnected"
    assert after["auto_sync_enabled"] is False, "断开了却还会自己跑"
    assert after["content_count"] == before["content_count"], (
        "断开把内容删掉了——断开是「别再替我去取」，不是「把我存的清掉」"
    )
    assert result["kept_content_count"] == before["content_count"]


def test_disconnect_is_idempotent(tmp_path) -> None:
    """再点一次不能报错。用户重复点是常态，不是异常。"""
    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    account_id = store.upsert_source_account(
        platform="reddit", external_account_id="spez", display_name="Reddit",
        auth_method="browser_session", auth_handle_ref=None,
        connection_state="connected",
    )
    store.disconnect_source_account(account_id)
    second = store.disconnect_source_account(account_id)
    assert second["found"] is True
    assert second["already_disconnected"] is True


def test_disconnecting_an_unknown_account_is_not_silently_ok(tmp_path) -> None:
    """不存在的账号要说不存在，不能回一个"成功了"。"""
    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    assert store.disconnect_source_account("acct_does_not_exist") == {"found": False}


def test_the_extension_clears_its_local_queue_too() -> None:
    """服务端标成断开、扩展队列里那条待办还在，下次唤醒照样会去跑。

    「服务端说断开了、插件还在同步」是最难查的那种不一致。
    """
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    block = background.split('"SA_DISCONNECT_ACCOUNT"', 1)[1][:800]
    assert "removeQueuedSync" in block, "断开没有清掉扩展本地队列"
    assert 'method: "DELETE"' in block


def test_disconnect_and_credential_revoke_stay_separate() -> None:
    """两件事分开：断开不顺手把托管的登录状态删掉。

    合并会让「我只是不想它再自动跑了」变成「我的登录状态也没了」。
    """
    api = API.read_text(encoding="utf-8")
    block = py_function(api, "def disconnect_account(")
    assert "credential_store.revoke" not in block
    assert "/v1/credentials" in block, "至少要在文档里指出撤销走的是另一条路"
