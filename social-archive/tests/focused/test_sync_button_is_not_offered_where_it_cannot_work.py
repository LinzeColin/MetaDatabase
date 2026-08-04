"""不给一个点下去必然失败的按钮（v0.0.0.7 / INV-ZERO-BARRIER）。

## 这条是 Owner 的原话逼出来的

> 「非常不好用 而且你的流程逻辑非常混乱 我都不知道应该怎么操作」

查到的直接原因：他有三个已连接的账号（小红书 / 抖音 / B站），界面给每个
都画了「立即同步」。点下去走到 `acquireRelationItems()` —— 那是个显式 stub
（T03 删掉 DOM 抓取器之后，T08 的替代品还没缝上），抛
`ACQUISITION_PATH_NOT_INSTALLED`。

而那个码**被别名成 SERVER_UNREACHABLE**，于是界面说：

    「暂时连不上服务器。你的数据没有丢，[ 重试 ]」

**他一遍遍重试一件永远不可能成功的事。**

## 修法有两层，缺一不可

1. 界面根本不画那颗按钮 —— 从源头不让人点到（本文件）
2. 万一还是走到那个码，它必须落进「这是我们的问题、别重试」
   （test_failure_copy_matrix 里那条）

## 能不能同步由**服务端**说了算

两个前端各维护一份「哪些平台能同步」必然漂开，那是又一处「看着接上了」。
`/v1/accounts` 的 supported_platforms 每项带 `sync_supported`，界面照着画。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PWA = ROOT / "apps/pwa/app.js"


def code_only(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//") and not line.lstrip().startswith("*")
    )


def test_the_server_declares_which_platforms_can_sync_today() -> None:
    from social_archive.account_sync import NOT_SYNCABLE_YET, PLATFORM_RELATIONS, SYNCABLE_NOW

    assert SYNCABLE_NOW, "没有任何平台被标为可同步——那界面什么都画不出来"
    # 走浏览器拦截路的四个国内源，本版本取数缝隙是 stub，必须**不在**可同步清单里
    for platform in ("xiaohongshu", "douyin", "kuaishou", "bilibili"):
        assert platform not in SYNCABLE_NOW, (
            f"{platform} 被标成可同步，而它的取数路是个 stub —— 用户会点到一个必然失败的按钮"
        )
        assert NOT_SYNCABLE_YET.get(platform), f"{platform} 没有写清「为什么不能」与「现在能做什么」"
        assert "保存到我的档案馆" in NOT_SYNCABLE_YET[platform], (
            f"{platform} 的说明没有给出现在真的能用的那个动作"
        )
    # Chrome 书签是实测跑通过的（T04，62 条）
    assert "generic-web" in SYNCABLE_NOW
    # 清单不能提到不存在的平台
    unknown = (SYNCABLE_NOW | set(NOT_SYNCABLE_YET)) - set(PLATFORM_RELATIONS)
    assert not unknown, f"清单里有平台目录中不存在的项：{sorted(unknown)}"


def test_the_api_hands_that_fact_to_the_client() -> None:
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    block = api.split("def accounts()", 1)[1][:900]
    assert '"sync_supported"' in block, "/v1/accounts 不告诉界面能不能同步"
    assert '"not_syncable_reason"' in block, "只说不能，不说为什么与现在能做什么"


def test_the_ui_does_not_draw_a_button_that_cannot_work() -> None:
    js = code_only(PWA.read_text(encoding="utf-8"))
    assert "state.platformSupport" in js, "界面没有读服务端给的平台能力"
    assert "sync_supported === false" in js, "界面没有据此分支"
    table = js.split("function renderSyncTable", 1)[1][:4000]
    branch_at = table.index("sync_supported === false")
    button_at = table.index('data-sync-account="${escapeHtml(account.id)}">立即同步')
    assert branch_at < button_at, (
        "「不能同步」的分支排在「立即同步」之后 —— 那颗按钮还是会被画出来"
    )
    assert "not_syncable_reason" in table, "没有把原因显示给用户"


def test_the_capability_comes_from_one_place_only() -> None:
    """两个前端各维护一份清单必然漂开。界面里不许出现硬编码的平台名单。"""
    js = code_only(PWA.read_text(encoding="utf-8"))
    table = js.split("function renderSyncTable", 1)[1][:4000]
    for hardcoded in ("xiaohongshu", "douyin", "kuaishou"):
        assert f'"{hardcoded}"' not in table.split("sync_supported")[1][:600], (
            "同步能力在界面里被硬编码了——服务端一改就对不上"
        )
