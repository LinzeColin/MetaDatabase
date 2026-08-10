r"""断开的账号不许摆一颗「立即同步」（2026-08-11）。

## 实测到的事故

今天读他生产库：三个账号全 `disconnected`、`auto_sync` 关着。
把这个形状喂给**生产下发的那份前端**、在真无头 Chrome 里读回 DOM，那一屏是：

    顶部    · 已存下的内容一条都没少 · 重新连接一次就会继续同步
    抖音    未连接  86 条   …  [ 立即同步 ] [ 删除并清空 ]
    B站     未连接  103 条  …  [ 立即同步 ] [ 删除并清空 ]

**顶上让他"重新连接"，行里给的却是"立即同步"。** 而在真镜像上实测：

    已连接   POST /v1/accounts/{id}/sync → 202，同步真的开始
    已断开   POST /v1/accounts/{id}/sync → 422 {"detail":"账号尚未连接，请先完成授权"}

也就是说他那两个最大的账号（86 条、103 条）上各摆着一颗**点下去必然失败**的
按钮。这正是验收里那句「绝不给一颗结构上不可能成功的按钮」。

## 为什么之前没被抓到

`syncAllAccounts` 早就按 `connection_state` 过滤了，行内那条 if/else 链却
从来没有一条判断连接状态——一个「注释写对了规则、条件写窄了一档」的老形状。
而已有的行渲染判据只问「删除按钮在不在」，没问「这一行还给了别的什么」。

## 它守什么

断开的账号：给「连接账号」，**不给** 立即同步 / 重试 / 暂停 / 继续。
已连接的账号：这些按钮该在的还在（否则这条判据就变成「把功能删光就能过」）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "apps/pwa/app.js"

# 点下去要走一条「活着的连接」的按钮。断开状态下一颗都不许出现。
NEEDS_A_LIVE_CONNECTION = ("data-sync-account=", 'data-control-action="retry"',
                           'data-control-action="pause"', 'data-control-action="resume"')


def _render(accounts: list[dict], runs: list[dict] | None = None) -> str:
    """把 renderSyncTable 抠出来在 node 里真跑，返回它写进表格的 HTML。

    这段夹具沿用 test_the_delete_button_shows_for_a_disconnected_account.py 那一份
    （`platformMeta` 里那个 `server` 少不得——少了它整段会走进「这个平台没有账号」，
    而那时候什么按钮都不画，判据会以为自己通过了）。
    """
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("  function renderSyncTable(")
    end = source.index("\n  function ", start + 10)
    body = source[start:end]
    labels_start = source.index("  const connectionLabels = {")
    labels_end = source.index("};", labels_start) + 2
    labels = source[labels_start:labels_end]
    sentence_start = source.index("  function runSentence(")
    run_sentence = source[sentence_start:source.index("\n  function ", sentence_start + 10)]
    script = f"""
    const state = {{
      accounts: {json.dumps(accounts)},
      syncRuns: {json.dumps(runs or [])},
      platformSupport: {{ douyin: {{ sync_supported: true }} }},
      extension: {{ detected: true, compatible: true, paired: true }},
    }};
    {labels}
    const platformOrder = ["douyin"];
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
    // 失败的 run 会走到它。**从真源里抠出来**，别在夹具里编一句——
    // 第一版没给它，node 报 `runSentence is not defined`，
    // 而那看起来和「判据发现了缺陷」一模一样。
    {run_sentence}
    // 它再往下依赖整本失败文案词典。**那本词典只决定那句话怎么说，
    // 不决定这一行给哪几颗按钮**——而这条判据断言的全是 `data-*` 动作标记。
    // 所以这里只桩住它，并把这个边界写在这儿：
    // 这条判据不检查失败时那句话对不对（那是 failure_copy 那几条判据的事）。
    function failureSentence() {{ return {{ text: "（夹具桩：这条判据不看这句话）" }}; }}
    document = {{ querySelectorAll: () => [] }};
    {body}
    renderSyncTable();
    console.log(html);
    """
    done = subprocess.run(["node", "-e", script], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr[-900:]
    return done.stdout


def _account(state: str) -> dict:
    return {"id": "acct_1", "platform": "douyin", "display_name": "抖音",
            "connection_state": state, "content_count": 86,
            "external_account_id": "owner"}


@pytest.mark.parametrize("run", [
    pytest.param(None, id="没有跑过"),
    pytest.param({"id": "run_1", "source_account_id": "acct_1", "status": "completed",
                  "discovered_count": 86, "imported_count": 86}, id="上次跑完了"),
    pytest.param({"id": "run_1", "source_account_id": "acct_1", "status": "failed",
                  "last_error_code": "PLATFORM_PERMISSION_MISSING"}, id="上次失败了"),
    pytest.param({"id": "run_1", "source_account_id": "acct_1", "status": "paused"},
                 id="上次暂停着"),
])
def test_a_disconnected_account_never_gets_a_button_that_cannot_work(run: dict | None) -> None:
    """**他现在就是这个状态**，而这四种历史他三个账号各占一种。"""
    html = _render([_account("disconnected")], [run] if run else [])
    offered = [marker for marker in NEEDS_A_LIVE_CONNECTION if marker in html]
    assert not offered, (
        f"断开的账号还摆着 {offered}——点下去服务端回 422「账号尚未连接」：\n{html[:500]}")
    assert "data-connect-platform=" in html and "连接账号" in html, (
        f"断开的账号没给他「连接账号」，那他没有任何一条出路：\n{html[:500]}")


@pytest.mark.parametrize("state", ["connected", "degraded"])
def test_a_live_account_still_gets_its_sync_button(state: str) -> None:
    """**反方向。** 不然「把按钮全删掉」也能让上面那条变绿。"""
    html = _render([_account(state)])
    assert "data-sync-account=" in html and "立即同步" in html, (
        f"connection_state={state} 的账号点不到「立即同步」了：\n{html[:500]}")


def test_a_live_account_that_failed_still_gets_retry() -> None:
    html = _render([_account("connected")],
                   [{"id": "run_1", "source_account_id": "acct_1", "status": "failed"}])
    assert 'data-control-action="retry"' in html, f"连着的账号失败后没有重试：\n{html[:500]}"


def test_the_delete_button_survives_this_change() -> None:
    """断开时那颗「删除并清空」还得在——他要靠它从零重来。"""
    html = _render([_account("disconnected")])
    assert "data-forget-account=" in html and "删除并清空" in html, html[:500]
