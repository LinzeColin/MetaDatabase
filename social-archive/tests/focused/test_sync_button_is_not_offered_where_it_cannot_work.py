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


def test_the_top_strip_does_not_say_everything_is_fine() -> None:
    """「N 个账号已连接」在一条都同步不动时是误导。

    Owner 的实况：三个已连接账号（小红书/抖音/B站），顶部写「3 个账号已连接」，
    读起来像一切正常——而那三个在本版本一条都同步不了。

    一个都同步不动时，顶部必须只说**现在真正能做的那一件事**。
    """
    js = code_only(PWA.read_text(encoding="utf-8"))
    block = js.split("function renderSyncSummary", 1)[1][:2200]
    assert "sync_supported !== false" in block, "顶部没有区分「已连接」与「同步得动」"
    assert "还不能自动同步" in block, "没有把差别说出来"
    assert "保存到我的档案馆" in block, "没有给出现在真正能做的那件事"
    # 顺序要紧：先判断「一个都动不了」，再走原来那套统计
    stuck_at = block.index("stuck > 0 && !syncable")
    generic_at = block.index("if (!state.accounts.length)")
    assert stuck_at < generic_at, "被通用分支抢先，特殊情况说不出来"


def test_a_sync_button_never_navigates_the_page_away_on_its_own() -> None:
    """按钮写「同步」就不能偷偷做「跳转」。

    Owner 的原话：「点击同步全部账号后就会跳转到莫名其妙的页面…
    怎么实际功能和显示文字还不一样」。

    原因：ensureExtensionReady 在插件未就绪时直接 `location.href =
    "/extension-install"`。那条 toast 也白搭——页面当场就跳走了，没人来得及读。

    跳不跳必须由用户决定，而且他得知道为什么。
    """
    js = code_only(PWA.read_text(encoding="utf-8"))
    block = js.split("async function ensureExtensionReady", 1)[1][:1800]
    jumps = [line.strip() for line in block.splitlines() if "location.href" in line]
    assert jumps, "这段里已经没有跳转了——判据失去依附，请重写"
    for line in jumps:
        assert "confirm(" in block.split(line)[0][-400:] or "if (confirm" in line, (
            f"这一处跳转没有先征求用户同意：{line}"
        )


def test_sync_all_counts_only_accounts_that_can_actually_sync() -> None:
    """「已将 3 个账号加入队列」然后什么也不发生，是最伤信任的一种假话。"""
    js = code_only(PWA.read_text(encoding="utf-8"))
    block = js.split("async function syncAllAccounts", 1)[1][:1400]
    assert "sync_supported !== false" in block, "把同步不了的账号也算进了队列数"
    assert "都还不能自动同步" in block, "一个都同步不动时没有明说"


def test_connect_is_not_offered_for_platforms_that_still_cannot_sync() -> None:
    """「连接账号 · 连接后自动首次全量同步」对同步不了的平台是假话。

    和「立即同步」那颗按钮同一种问题，只是出现在未连接状态下。
    连了小红书之后一条也同步不了——那颗按钮不该存在。
    """
    js = code_only(PWA.read_text(encoding="utf-8"))
    block = js.split("function renderSyncTable", 1)[1][:5000]
    empty_branch = block.split("if (!accounts.length)", 1)[1][:1800]
    assert "sync_supported === false" in empty_branch, "未连接分支没有区分能不能同步"
    guard_at = empty_branch.index("sync_supported === false")
    connect_at = empty_branch.index('data-connect-platform="${server}">连接账号')
    assert guard_at < connect_at, "「连接账号」仍会画给同步不了的平台"
    assert "连接后自动首次全量同步" in empty_branch, "判据失去依附：那句话已经不在了"


def test_the_queue_itself_refuses_before_touching_any_tab() -> None:
    """藏起按钮不够——**真正干活的那条路必须也拦**。

    Owner 的原话：「软件抽风 每次都是把目标网页开了关关了开」。

    机制：每分钟一次的 processSyncQueue 取出任务 → runBrowserAccountSync →
    navigateMirrorTab 用 `chrome.tabs.update(tabId, { url, active: true })`
    **把用户的标签页导航到收藏页并切到前台** → acquireRelationItems 抛错 →
    下一分钟再来一次。

    我上一轮只在界面上藏了「立即同步」，队列照跑。**藏按钮只挡住了入口之一。**
    """
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    text = code_only(background)
    assert "async function platformCanSyncNow(" in text, "扩展不问服务端这个平台能不能同步"

    # 入队那一层：同步不了的根本不进队列
    enqueue = text.split("async function enqueueAllAccounts", 1)[1][:900]
    assert "platformCanSyncNow" in enqueue, "同步不了的平台仍会被放进队列"

    # 干活那一层：碰标签页之前先拦
    run = text.split("async function runBrowserAccountSync", 1)[1][:1200]
    assert "platformCanSyncNow" in run, "真正干活那条路没拦"
    guard_at = run.index("platformCanSyncNow")
    nav_at = run.index("navigateMirrorTab") if "navigateMirrorTab" in run else len(run)
    assert guard_at < nav_at, "拦在导航之后，标签页已经被抢了"


def test_the_capability_is_not_duplicated_inside_the_extension() -> None:
    """能力由服务端说了算。扩展里再维护一份名单必然漂开。"""
    text = code_only((ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8"))
    block = text.split("async function platformCanSyncNow", 1)[1][:700]
    for hardcoded in ("xiaohongshu", "douyin", "kuaishou", "bilibili"):
        assert f'"{hardcoded}"' not in block, "扩展里硬编码了平台名单——服务端一改就对不上"
    assert "supported_platforms" in block, "没有读服务端下发的能力"
