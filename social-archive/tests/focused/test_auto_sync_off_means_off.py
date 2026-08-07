r"""界面写着「自动同步=关」，六小时的定时任务就不许去动它（2026-08-07）。

## 怎么发现的

从生产回读他的账号，三行都是 `auto_sync_enabled=False`。顺着问下去：
**他重新连接之后自动同步会不会自己打开**（会——upsert 默认 True，同一行不分叉），
再顺着问**谁在读这个字段**——`enqueueAllAccounts` 不读。它只看
`connection_state in (connected, degraded)`。

而 `set_source_account_state(id, "connected", verified=True)`
（account_sync.py，一次同步成功之后调）**只改状态、不碰 auto_sync_enabled**。
于是可以长出「已连接 + 自动同步=关」这一行：弹窗和资料库都对他说
「自动同步=关」，而每 6 小时的 `sa-account-sync` 照样替他跑。

**产品说的和产品做的不一致，而他没有别的办法发现。**

## 判据打在哪

不打在源码文本上（那种判据我改一次实现就假红/假绿），而是**把 background.js
真的加载进 Node、用假的 chrome.* 和假的服务端跑一遍 `enqueueAllAccounts`**，
看进队列的到底是哪几个账号。夹具复用
`test_sync_queue_survives_worker_death.py` 那套 harness——同一个真身，
不另造一个更干净的。

## 只挡显式的 false

字段缺失（老版本服务端、将来新增的账号类型）按「开」算。反过来会把他所有的
自动同步**静默关掉**，那是更坏的方向——这个仓在「空默认值吞掉不知道」上栽过。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = ROOT / "apps/browser-extension/background.js"

_spec = importlib.util.spec_from_file_location(
    "_sync_queue_harness", Path(__file__).parent / "test_sync_queue_survives_worker_death.py")
_harness = importlib.util.module_from_spec(_spec)
sys.modules["_sync_queue_harness"] = _harness
_spec.loader.exec_module(_harness)


ACCOUNTS = [
    {"id": "acc-on", "platform": "bilibili", "external_account_id": "browser-session",
     "connection_state": "connected", "auto_sync_enabled": True},
    {"id": "acc-off", "platform": "douyin", "external_account_id": "browser-session",
     "connection_state": "connected", "auto_sync_enabled": False},
    {"id": "acc-gone", "platform": "xiaohongshu", "external_account_id": "browser-session",
     "connection_state": "disconnected", "auto_sync_enabled": False},
]


def _queued(accounts: list[dict]) -> list[str]:
    """跑一次定时同步，返回真正进了队列的账号 id。"""
    import json as _json

    body = r"""
    const storage = {}, alarms = {};
    const ACCOUNTS = __ACCOUNTS__;
    const worker = bootWorker(storage, alarms, { onFetch: (url) => {
      if (url.includes('/v1/accounts')) return { items: ACCOUNTS };
      if (url.includes('/v1/sync-runs')) return { items: [] };
      return { items: [] };
    }});
    await worker.enqueueAllAccounts('scheduled');
    const queue = storage['sa.syncQueue'] || storage['sa_sync_queue'] || [];
    const key = Object.keys(storage).find(k => Array.isArray(storage[k])
                  && storage[k].some(i => i && i.accountId));
    const rows = key ? storage[key] : queue;
    console.log(JSON.stringify((rows || []).map(i => i.accountId)));
    """.replace("__ACCOUNTS__", _json.dumps(accounts))
    return _harness._node(_harness._script(body)) or []


@pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")
def test_the_scheduled_run_skips_an_account_whose_auto_sync_is_off() -> None:
    """**正例和反例在同一次里**：开着的进队列，关着的不进。

    只测「关着的不进」不够——一个把所有账号都挡掉的实现也能过。
    """
    queued = _queued(ACCOUNTS)
    assert "acc-on" in queued, (
        f"自动同步开着的账号没进队列：{queued}——**这个方向坏掉，他连不上任何东西**")
    assert "acc-off" not in queued, (
        f"界面上写着「自动同步=关」，定时任务却把它排进了队列：{queued}——"
        "产品说的和产品做的不一致，而他没有别的办法发现")
    assert "acc-gone" not in queued, f"已断开的账号进了队列：{queued}"


@pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")
def test_a_missing_field_counts_as_on_not_off() -> None:
    """**字段缺失按「开」算。**

    反过来会把他所有的自动同步静默关掉——一个读不到的字段不该等于
    「他关掉了」。这个仓在「空默认值吞掉不知道」上栽过很多次。
    """
    accounts = [{"id": "acc-old", "platform": "bilibili",
                 "external_account_id": "browser-session",
                 "connection_state": "connected"}]          # 没有 auto_sync_enabled
    assert "acc-old" in _queued(accounts), (
        "服务端没给这个字段，扩展就把他的自动同步关了——"
        "缺失是「不知道」，不是「关」")
