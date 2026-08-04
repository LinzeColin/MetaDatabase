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

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PWA = ROOT / "apps/pwa/app.js"


def _function_body(js: str, name: str) -> str:
    """取一个顶层函数的函数体，切到下一个顶层 function 为止。"""
    body = js.split(f"function {name}", 1)[1]
    nxt = re.search(r"\n  (?:async )?function ", body)
    return body[: nxt.start()] if nxt else body


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
    # **切到函数末尾，不用魔法数字。** 原来切 4000 字符；我在函数开头加了
    # 一段注释，立即同步那颗按钮就被挤出窗口，判据当场 ValueError——
    # 而代码是对的。判据自己钉在长度上，就会被无关的编辑打断。
    table = _function_body(js, "renderSyncTable")
    branch_at = table.index("sync_supported === false")
    button_at = table.index('data-sync-account="${escapeHtml(account.id)}">立即同步')
    assert branch_at < button_at, (
        "「不能同步」的分支排在「立即同步」之后 —— 那颗按钮还是会被画出来"
    )
    assert "not_syncable_reason" in table, "没有把原因显示给用户"


def test_the_capability_comes_from_one_place_only() -> None:
    """两个前端各维护一份清单必然漂开。界面里不许出现硬编码的平台名单。"""
    js = code_only(PWA.read_text(encoding="utf-8"))
    # **切到函数末尾，不用魔法数字。** 原来切 4000 字符；我在函数开头加了
    # 一段注释，立即同步那颗按钮就被挤出窗口，判据当场 ValueError——
    # 而代码是对的。判据自己钉在长度上，就会被无关的编辑打断。
    table = _function_body(js, "renderSyncTable")
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
    assert "async function platformCapability(" in text, "扩展不问服务端这个平台的能力"
    assert "async function platformCanSyncNow(" in text, "少了「能不能同步」这一问"

    # 入队那一层：同步不了的根本不进队列
    enqueue = text.split("async function enqueueAllAccounts", 1)[1][:900]
    assert "platformCanSyncNow" in enqueue, "同步不了的平台仍会被放进队列"

    # 干活那一层：碰标签页之前先拦
    run = text.split("async function runBrowserAccountSync", 1)[1][:2400]
    assert "platformCapability" in run, "真正干活那条路没拦"
    guard_at = run.index("platformCapability")
    nav_at = run.index("navigateMirrorTab") if "navigateMirrorTab" in run else len(run)
    assert guard_at < nav_at, "拦在导航之后，标签页已经被抢了"


def test_the_capability_is_not_duplicated_inside_the_extension() -> None:
    """能力由服务端说了算。扩展里再维护一份名单必然漂开。"""
    text = code_only((ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8"))
    block = text.split("async function platformCapability", 1)[1][:900]
    for hardcoded in ("xiaohongshu", "douyin", "kuaishou", "bilibili"):
        assert f'"{hardcoded}"' not in block, "扩展里硬编码了平台名单——服务端一改就对不上"
    assert "supported_platforms" in block, "没有读服务端下发的能力"


def test_platforms_the_server_syncs_itself_never_touch_a_tab() -> None:
    """**上一轮只修了一半。**

    上一轮挡住的是「服务端说同步不了」的平台（小红书/抖音/快手/B站）。
    可 syncAccountById 里除了 Chrome 书签之外**一律**走 runBrowserAccountSync，
    而 x / reddit / instagram 明明在服务端的 SERVER_ACCOUNT_CONNECTORS 里、
    根本不需要浏览器参与。

    实测（2026-08-04，真 Chrome，stub 掉 chrome.tabs.update 记录调用）：
    对 x 跑一次 runBrowserAccountSync，**用户的标签页被抢了 2 次**——
    先导到 x.com/i/bookmarks，再导到 x.com/home，两次都是 active: true。
    而且它连异常都没抛，队列会认为这次跑完了、下次接着来。

    也就是说 Owner 那句「每次都是把目标网页开了关关了开」，在他连上 X 的
    那一刻就会原样复发。
    """
    text = code_only((ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8"))

    # 分流那一层：服务端能干的，走服务端接口，不进浏览器路
    route = text.split("async function syncAccountById", 1)[1][:2400]
    assert "serverHandled" in route, "分流层不看服务端是否自己就能同步"
    server_at = route.index("serverHandled")
    browser_at = route.index("runBrowserAccountSync")
    assert server_at < browser_at, "先掉进浏览器路了，分流没起作用"
    assert "startServerSideSync" in route[:browser_at], "分流到了服务端之外的什么地方"
    # 交接的实现自己得真的去调那个接口——判据钉在机制上，不钉在某个恰好
    # 出现在附近的字符串上。（第一版就钉错了：把 `/sync` 钉在分流块里，
    # 把那段逻辑抽成函数之后判据立刻转红，而代码是对的。）
    handoff = text.split("async function startServerSideSync", 1)[1][:600]
    assert "/sync" in handoff, "交给服务端的那个函数没有调服务端的同步接口"
    assert "chrome.tabs" not in handoff, "交给服务端的路上还在碰标签页"

    # 干活那一层：第二道拦截，防 chrome.storage 里压着**升级前**入队的旧任务。
    # 注意它不是「拒绝」而是「改交给服务端」——拒绝会写成一次
    # completeness=failed 的回执，用户看到一次失败，可他什么都没做错，
    # 是我们路由错了；而且那要往冻结词典里加一个新句子。
    run = text.split("async function runBrowserAccountSync", 1)[1][:2400]
    assert "startServerSideSync" in run, "旧任务仍能从这条路抢标签页"
    guard_at = run.index("startServerSideSync")
    nav_at = run.index("navigateMirrorTab") if "navigateMirrorTab" in run else len(run)
    assert guard_at < nav_at, "拦在导航之后，标签页已经被抢了"


def test_the_server_publishes_who_handles_each_platform() -> None:
    """能力仍然只有一处真源：服务端说了算，扩展照做。"""
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert '"server_handled": platform in SERVER_ACCOUNT_CONNECTORS' in api, (
        "/v1/accounts 不下发「这个平台由谁同步」，扩展只能猜——而它上次就猜错了"
    )


def test_the_server_handoff_exists_once_not_twice() -> None:
    """两处都要把活交给服务端，但**实现只能有一份**。

    两份同样的逻辑，只有一份会被改到，另一份就成了下一次「看着接上了」。
    """
    text = code_only((ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8"))
    assert text.count("async function startServerSideSync") == 1, "交给服务端的实现不止一份"
    assert text.count("/v1/accounts/${encodeURIComponent(accountId)}/sync") == 1, (
        "调服务端同步接口的地方不止一处——两份会漂开"
    )


def test_it_asks_can_it_sync_before_asking_who_handles_it() -> None:
    """顺序要紧，反了 bilibili 就出事。

    bilibili 同时满足两件事：
      · server_handled = true（在服务端的 SERVER_ACCOUNT_CONNECTORS 里）
      · sync_supported = false（不在 SYNCABLE_NOW 里）

    先看 serverHandled 就会把它交给服务端，而服务端对它同样没有能用的
    取数实现——那次 run 停在半路，界面一直转圈。

    **「服务端登记了这个平台」不等于「服务端做得成」。**
    """
    text = code_only((ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8"))
    route = text.split("async function syncAccountById", 1)[1][:2600]
    can_at = route.index("capability.canSync")
    who_at = route.index("capability.serverHandled")
    assert can_at < who_at, "先问了「谁来干」，同步不了的平台会被交给一个同样干不成的服务端"


def test_connect_is_gated_on_can_i_connect_not_on_can_i_sync() -> None:
    """**「同步不了」不等于「连了没用」。**

    把 x / instagram 移出 SYNCABLE_NOW 之后，renderSyncTable 里那段
    「同步不了的平台，连了也没用」顺手把它们的**连接入口**也一起关掉了。
    一次改动，两个后果，而第二个我没看见。

    那句话对国内四家是真的——它们的 Cookie 一步都不离开浏览器，服务端
    根本不接收（credentials.DOMESTIC_PLATFORMS 明确拒绝）。
    **对 x / instagram 是假的**：托管的登录状态会被 worker.py 取原文件
    那条路用到（CredentialStore.materialize → capture_url(cookies_path=…)）。
    """
    js = code_only(PWA.read_text(encoding="utf-8"))
    table = _function_body(js, "renderSyncTable")
    assert "connect_supported" in table, "连接入口仍然只看「能不能同步」"
    branch = table.split("sync_supported === false", 1)[1][:1600]
    assert "connect_supported" in branch, "同步不了那一支里没有再问一句「那连得上吗」"


def test_the_server_publishes_whether_connecting_is_worth_it() -> None:
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert '"connect_supported": platform in SYNCABLE_NOW or platform in CUSTODIAL_PLATFORMS' in api, (
        "服务端不下发「连它有没有用」，界面只能拿「能不能同步」凑合——那次就凑错了"
    )


def test_the_extension_options_page_makes_the_same_distinction() -> None:
    """两个界面各有一份，修一边等于没修。

    第一轮改「同步不了就不给按钮」时，我只改了网页那侧，扩展设置页
    原样留着同样的三处假话——那道门（find_affordances_the_backend_says_cannot_work）
    就是为了不再漏掉另一半。这次的「连了有没有用」也一样，两边都要有。
    """
    options = code_only((ROOT / "apps/browser-extension/options.js").read_text(encoding="utf-8"))
    assert "connect_supported" in options, "扩展设置页仍然只看「能不能同步」"
    block = options.split("const syncable", 1)[1][:2200]
    assert "connectable" in block, "算出来了却没在分支里用"
    not_syncable_branch = block.split("const action=!syncable", 1)[1][:600]
    assert "connectable" in not_syncable_branch, (
        "同步不了那一支里没有再问一句「那连得上吗」——x / instagram 的连接入口又没了"
    )
