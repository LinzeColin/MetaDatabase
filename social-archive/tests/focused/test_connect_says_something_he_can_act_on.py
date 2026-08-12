"""没拿到权限时，连接要说人话，不能把 Chrome 的英文原样甩给他（2026-08-10）。

## 第三处，同一条规矩

`chrome.permissions.request` 在 MV3 的 service worker 里**一定抛**
（没有用户手势，即使权限刚被授予过）。今天前两处已经修了：

    connectChromeBookmarks           bookmarks   裸 request、没有 catch
    connectPlatformSessionByCookies  cookies     裸 request、有 catch

第三处藏在 `shared.js:requestPlatformPermission` 的调用方里。那个帮手本身
2026-08-06 就改成「先 contains 再 request」了，**但它最后那一句 request
仍然会抛**，而三个调用方里只有两个接了 `.catch(() => false)`：

    background.js:314   installNetObserverForTab      .catch(() => false)  ✓
    background.js:1383  bilibili 注入前                .catch(() => false)  ✓
    background.js:997   **connectBrowserPlatform**     没有 catch           ✗

而 `connectBrowserPlatform` 正是 bilibili / 小红书 / 抖音 / 快手 / Reddit /
Instagram **重新连接**走的那一条——也就是 Owner 现在唯一要做的那件事。
授权真的没拿到时，他看到的会是

    This function must be called during a user gesture

而不是「未获得B站页面读取权限」。**做不到不是罪，做不到却说不清才是。**

## 为什么以前测不出来

`test_sync_queue_survives_worker_death.py` 那个假 chrome 原来把
`permissions.request` 桩成 `async () => true`——夹具把用户必须自己挣的那一下
直接给了。今天改成像真 service worker 一样抛之后，这条判据才有意义。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = ROOT / "apps/browser-extension/background.js"
SHARED = ROOT / "apps/browser-extension/shared.js"

_spec = importlib.util.spec_from_file_location(
    "_sync_queue_harness", Path(__file__).parent / "test_sync_queue_survives_worker_death.py")
_harness = importlib.util.module_from_spec(_spec)
sys.modules["_sync_queue_harness"] = _harness
_spec.loader.exec_module(_harness)

pytestmark = pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")


def test_connecting_without_permission_returns_a_chinese_sentence() -> None:
    """**没权限是一种正常结局，不是一次崩溃。**

    把 `chrome.permissions.contains` 拨成 false（真实场景：他在弹框里点了
    「不允许」，或者面板那一步没走成），走一次 `connectBrowserPlatform`。
    """
    body = r"""
    const storage = {}, alarms = {};
    const worker = bootWorker(storage, alarms, { onFetch: () => ({ items: [] }) });
    // **他没给授权**——这一步之后，service worker 里那句 request 一定抛。
    worker.chrome.permissions.contains = async () => false;
    let out;
    try { out = await worker.connectBrowserPlatform('bilibili'); }
    catch (error) { out = { threw: String(error && error.message || error) }; }
    console.log(JSON.stringify(out));
    """
    result = _harness._node(_harness._script(body))
    assert "threw" not in result, (
        f"连接抛出去了：{result['threw']!r}——面板会把这句话原样显示给他。"
        "`SA.requestPlatformPermission` 最后那一句 request 在 service worker 里必抛，"
        "调用方要么接住，要么让那个帮手自己接住")
    assert result.get("state") == "unauthorized", result
    assert "权限" in str(result.get("error") or ""), (
        f"没权限时说的不是人话：{result.get('error')!r}")


def test_the_helper_itself_swallows_the_gesture_error() -> None:
    """**在一处接住，好过在三处各接一次。**

    三个调用方里原来只有两个接了 catch；漏掉的恰好是重新连接那一条。
    让帮手自己接住，就不会再有"第四个调用方忘了接"。
    """
    shared = SHARED.read_text(encoding="utf-8")
    # **切到函数真正的结尾，别切一个固定字数的窗口。**
    # 第一版切 400 字，而函数里那段解释「为什么必须走 ensurePermission」的注释
    # 比 400 字长，于是判据看不见后面那一行——窗口开太小，这个仓栽过。
    rest = shared.split("async function requestPlatformPermission", 1)[1]
    body = rest.split("\n  async function ", 1)[0].split("\n  function ", 1)[0]
    assert "ensurePermission" in body, (
        "requestPlatformPermission 没有走 ensurePermission——"
        "那它最后那一句 request 仍然会在 service worker 里抛出去")


def test_a_granted_platform_still_connects() -> None:
    """**正例必须是绿的。** 一个"永远说没授权"的实现同样是坏的。"""
    body = r"""
    const storage = {}, alarms = {};
    const worker = bootWorker(storage, alarms, { onFetch: (url) => {
      if (url.includes('/connect/') && url.includes('/complete'))
        return { account_id: 'acc-b', first_sync: { sync_run_id: 'run-1' } };
      if (url.includes('/connect/start')) return { connection_ref: 'ref-1' };
      return { items: [] };
    }});
    let out;
    try { out = await worker.connectBrowserPlatform('bilibili'); }
    catch (error) { out = { threw: String(error && error.message || error) }; }
    console.log(JSON.stringify({ state: out && out.state, threw: out && out.threw }));
    """
    result = _harness._node(_harness._script(body))
    assert not result.get("threw"), result
    assert result.get("state") != "unauthorized", (
        f"权限齐了还说没授权：{result}——这条判据把好实现也判死了")
