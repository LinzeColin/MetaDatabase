r"""说明书承诺「连上之后自动同步会跟着恢复」——这条断言就是它的主人（2026-08-12）。

## 为什么要单开一条

他那三个账号今天在生产上是这个样子（实测，不是推断）：

    bilibili / douyin / xiaohongshu   connection_state=disconnected   auto_sync_enabled=0

而 `docs/使用说明.md` 写着「连上之后自动同步会跟着恢复」。这句话的真假
取决于一条**四段的链**，中间任何一段断了，他都会看到「已连接」而永远等不到条目：

    他点「连接账号」
      → background.js 送 `auto_sync_enabled: true`（5 个连接点都送）
      → api.py `bool(metadata.get("auto_sync_enabled", True))`
      → account_sync.complete_connection(auto_sync_enabled=…)
      → RuntimeStore.upsert_source_account 落库
      → 6 小时那个闹钟的过滤器 `item.auto_sync_enabled !== false` 重新收下它

`disconnect_source_account` 是**故意**把它设成 0 的（「不再自己跑」），
所以恢复不是自动的，全靠重连那一路把 true 送回来。

## 已有的测试盖不住这里

`test_everything_connected_can_be_disconnected.py` 只走到「断开」为止，
断言的是 `auto_sync_enabled is False`——**断开这一半是有主的，回来这一半没有**。
一个只测得出「关得掉」的测试，正好会在「打不开」时全绿。

## 这里为什么用 `is False` / `is True` 而不是 `== 0`

`list_source_accounts` 出口做了 `bool(...)` 转换，而扩展那边的过滤器写的是
`!== false`。**JS 里 `0 !== false` 是 true**——如果哪天出口的 bool() 掉了，
落库的 0 会原样送到浏览器，过滤器就会把一个「自动同步=关」的账号照样收下，
那正是 2026-08-07 修掉的那个缺陷反向复发。`is` 比较连这个都一起钉住。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.db import RuntimeStore  # noqa: E402

ACCOUNT = dict(platform="bilibili", external_account_id="him", display_name="B站",
               auth_method="browser_session", auth_handle_ref=None)


@pytest.fixture()
def store(tmp_path: Path) -> RuntimeStore:
    made = RuntimeStore(tmp_path / "runtime.sqlite3")
    made.initialize()
    return made


def _row(store: RuntimeStore, account_id: str) -> dict:
    return {a["id"]: a for a in store.list_source_accounts()}[account_id]


def test_reconnecting_turns_auto_sync_back_on(store: RuntimeStore) -> None:
    """他这三个账号今天就停在中间那一步上。"""
    account_id = store.upsert_source_account(
        connection_state="connected", auto_sync_enabled=True, **ACCOUNT)
    assert _row(store, account_id)["auto_sync_enabled"] is True

    store.disconnect_source_account(account_id)
    assert _row(store, account_id)["connection_state"] == "disconnected"
    # 这一条不是顺手写的：断开如果**没有**关掉自动同步，
    # 下面那个「重连打开了它」就成了废话——它本来就是开的。
    assert _row(store, account_id)["auto_sync_enabled"] is False

    # 他点「连接账号」之后服务端收到的就是这一组参数。
    store.upsert_source_account(
        connection_state="connected", auto_sync_enabled=True, **ACCOUNT)
    back = _row(store, account_id)
    assert back["connection_state"] == "connected"
    assert back["auto_sync_enabled"] is True


def test_the_flag_survives_as_a_real_bool_not_a_zero(store: RuntimeStore) -> None:
    """出口必须是真的 bool。

    落库是 INTEGER。**浏览器那头的过滤器写的是 `!== false`，而 JS 里
    `0 !== false` 为真**——出口一旦漏掉 `bool()`，一个「自动同步=关」的账号
    会被定时任务照样收下，用户在界面上看到「关」，产品每 6 小时替他跑一次。
    """
    account_id = store.upsert_source_account(
        connection_state="connected", auto_sync_enabled=False, **ACCOUNT)
    value = _row(store, account_id)["auto_sync_enabled"]
    assert value is False, f"出口给的是 {value!r}（{type(value).__name__}），不是 bool"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
