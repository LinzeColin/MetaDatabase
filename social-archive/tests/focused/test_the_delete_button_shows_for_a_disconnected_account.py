r"""他那三个账号都是 disconnected——删除按钮得真的画出来（2026-08-10）。

Owner 要这颗按钮是为了「从零测试能不能用」。而他生产上的抖音/B站/小红书
**全是 `disconnected`、自动同步关着**（8-04 之后就没连过）。
所以「按钮在代码里」不等于「他屏幕上有」：要是它只画给已连接的账号，
这颗按钮对他恰好一个都不出现。

这个仓已有的那条判据是**切文本**看的（`js_function` + 字符串位置），
那种查法回答不了「这一行到底渲染成什么样」。这里把 `renderSyncTable`
抠出来在 node 里真跑，喂他真实的账号状态。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "apps/pwa/app.js"


def _render(accounts: list[dict], runs: list[dict] | None = None) -> str:
    """把 renderSyncTable 抠出来跑一遍，返回它写进表格的 HTML。"""
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("  function renderSyncTable(")
    end = source.index("\n  function ", start + 10)
    body = source[start:end]
    labels_start = source.index("  const connectionLabels = {")
    labels_end = source.index("};", labels_start) + 2
    labels = source[labels_start:labels_end]
    script = f"""
    const state = {{
      accounts: {json.dumps(accounts)},
      syncRuns: {json.dumps(runs or [])},
      platformSupport: {{ douyin: {{ sync_supported: true }} }},
      extension: {{ detected: true, compatible: true, paired: true }},
    }};
    // **真源里那张表也抠出来**，别在夹具里编一份——编的那份和真的漂开时
    // 这条判据会以为自己在测真东西。
    {labels}
    const platformOrder = ["douyin"];
    // **`server` 不能少**：少了它 `accounts.filter(a => a.platform === server)`
    // 永远为空，整段走进「这个平台没有账号」那一支——
    // 我第一版就是这样，差点把夹具的毛病报成产品缺陷。
    const platformMeta = {{ douyin: {{ label: "抖音", server: "douyin" }} }};
    const serverToUiPlatform = {{ douyin: "douyin" }};
    const uiToServerPlatform = {{ douyin: "douyin" }};
    let html = "";
    function $(id) {{ return {{ set innerHTML(v) {{ html = v; }}, get innerHTML() {{ return html; }} }}; }}
    function escapeHtml(s) {{ return String(s); }}
    function platformLogo() {{ return ""; }}
    function formatTime() {{ return ""; }}
    function formatDate() {{ return ""; }}
    function archiveLabel(v) {{ return String(v || ""); }}
    function relationLabel(v) {{ return String(v || ""); }}
    function latestRunFor(id) {{ return state.syncRuns.find(r => r.source_account_id === id) || null; }}
    document = {{ querySelectorAll: () => [] }};
    {body}
    renderSyncTable();
    console.log(html);
    """
    done = subprocess.run(["node", "-e", script], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr[-900:]
    return done.stdout


def _account(state: str = "disconnected") -> dict:
    return {"id": "acct_1", "platform": "douyin", "display_name": "抖音",
            "connection_state": state, "content_count": 86,
            "external_account_id": "owner"}


@pytest.mark.parametrize("state", ["disconnected", "connected", "degraded"])
def test_the_delete_button_is_rendered_whatever_the_connection_state(state: str) -> None:
    """**他那三个都是 disconnected。** 只画给已连接的话，这颗按钮对他一个都不出现。"""
    html = _render([_account(state)])
    assert "data-forget-account=" in html, (
        f"connection_state={state} 时删除按钮没画出来——他点不到：\n{html[:400]}")
    assert "删除并清空" in html, html[:400]


def test_it_is_not_offered_while_a_sync_is_running() -> None:
    """跑到一半时该点的是「取消」，不是删除——两颗摆一起会让人选错。"""
    html = _render([_account("connected")],
                   [{"id": "run_1", "source_account_id": "acct_1", "status": "scanning"}])
    assert "data-forget-account=" not in html, (
        "同步跑着的时候还给删除按钮——他可能在数据进到一半时点它")
