from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"
PWA = ROOT / "apps/pwa/app.js"


def test_pwa_and_popup_route_account_sync_through_extension_runtime():
    pwa = PWA.read_text(encoding="utf-8")
    bridge = (EXT / "bridge.js").read_text(encoding="utf-8")
    popup = (EXT / "popup.js").read_text(encoding="utf-8")
    assert 'postToExtension("SA_SYNC_ACCOUNT"' in pwa
    assert 'postToExtension("SA_SYNC_ALL_ACCOUNTS"' in pwa
    assert 'message.type === "SA_SYNC_ACCOUNT"' in bridge
    assert 'type: "SA_SYNC_ACCOUNT"' in bridge
    assert 'type: "SA_SYNC_ALL_ACCOUNTS"' in popup
    assert "/v1/accounts/${encodeURIComponent(accountId)}/sync" not in pwa


def test_pwa_pings_the_bridge_and_rejects_unpaired_or_wrong_version_extensions():
    pwa = PWA.read_text(encoding="utf-8")
    bridge = (EXT / "bridge.js").read_text(encoding="utf-8")
    # 版本跟着仓根 VERSION 走，不再逐字钉死。**钉死的断言只能证明"没人动过它"**，
    # 而这里恰恰相反：界面上原先一直显示 v0.0.0.6，正是因为没人动它。
    expected_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert f'const PRODUCT_VERSION = "{expected_version}"' in pwa, (
        f"PWA 自报的版本与 VERSION（{expected_version}）不一致——界面会显示错的版本号"
    )
    assert 'postToExtension("SA_PING", {}, 1500)' in pwa
    assert 'data.type !== "SA_BRIDGE_READY"' in pwa
    # v0.0.0.7 / T03：不再把用户丢去设置页手抄配对码；未连接时就地取凭据接上。
    assert 'await postToExtension("SA_ADOPT_TOKEN"' in pwa
    assert 'location.href = "/extension-install"' in pwa
    assert 'message.type === "SA_PING"' in bridge
    assert 'post("SA_PONG"' in bridge


def test_install_or_update_reconnects_existing_pwa_bridge_without_reloading_or_touching_platform_tabs():
    background = (EXT / "background.js").read_text(encoding="utf-8")
    bridge = (EXT / "bridge.js").read_text(encoding="utf-8")
    assert "const PWA_BRIDGE_URL_PATTERNS" in background
    assert '"https://social-archive.linzezhang.com/*"' in background
    assert '"http://127.0.0.1:8765/*"' in background
    assert '"http://localhost:8765/*"' in background
    assert "async function reconnectOpenPwaBridgeTabs()" in background
    assert "chrome.tabs.query({ url: PWA_BRIDGE_URL_PATTERNS })" in background
    assert 'tab.status === "complete"' in background
    assert 'files: ["bridge.js"]' in background
    assert 'if (details.reason === "install" || details.reason === "update")' in background
    assert "await reconnectOpenPwaBridgeTabs();" in background
    # **这一条原来是一刀切：`"chrome.tabs.reload" not in background`。**
    #
    # 它要守的是「装/更新插件时不能悄悄刷新用户的标签页」——那个用意完全正确，
    # 悄悄重载会丢掉用户正在看的东西。但一刀切也把**用户自己点出来的**刷新
    # 一起禁了：诊断按钮必须先重载页面，否则注入进去的新观察器会被幂等守卫
    # 直接返回，实际生效的还是旧的那份（实测：抓 0 条而自报 installed/ready 全 true）。
    #
    # 所以收窄到它真正要守的那件事：**每一处 reload 都必须在用户发起的分支里**。
    reloads = [
        line.strip() for line in background.splitlines() if "chrome.tabs.reload" in line
    ]
    for line in reloads:
        before = background.split(line)[0]
        # 两种写法都算：处理器里判 message.diagnostic，
        # 挪出来的 installNetObserverForTab 里判它自己那个入参 diagnostic。
        # **写法可以变，「必须由用户发起」这件事不能变。**
        # v0.0.0.21 加了第三种：按形状读列表（shapeMode）。它也必须刷新——
        # 观察器要比页面自己的 fetch 先就位，不刷新就一条也抓不到
        # （实测：自报 installed/ready 全 true，而 netCaptureBuffer 是空的）。
        #
        # **放它进来的前提写在下一条断言里**：那条路不许复用用户自己开着的页面。
        # 只放宽这里而不验那个前提的话，就等于允许刷新他正在看的小红书页。
        assert ("message.diagnostic === true" in before[-800:]
                or "if (diagnostic) {" in before[-800:]
                or "if (diagnostic || shapeMode) {" in before[-900:]), (
            f"这一处 reload 不在用户发起的诊断分支里：{line}"
        )

    # **按形状读的平台，不许复用用户自己开着的那个页面。**
    #
    # 上面刚放宽了「shapeMode 也能刷新」，而刷新他正开着的小红书页
    # = 打断他正在看的东西、丢掉滚动位置。两条必须成对存在：
    # 只有「同步自己开的后台页」才谈得上随便刷。
    if "shapeMode" in background:
        assert "SHAPE_READ_PLATFORMS[account.platform]" in background, (
            "按形状读的平台没有和「不复用已有标签页」绑在一起——"
            "那条路会刷新他正开着的平台页"
        )
        assert "if (!tab && !ownTabOnly)" in background, (
            "复用已有标签页那一行没有排除按形状读的平台"
        )
    # 安装/更新那条路仍然不许碰任何标签页
    install_path = background.split("async function reconnectOpenPwaBridgeTabs()", 1)[1][:800]
    assert "chrome.tabs.reload" not in install_path, "装/更新时又去重载标签页了"
    assert 'const BRIDGE_STATE_KEY = "__socialArchiveExtensionBridgeState"' in bridge
    assert "window.removeEventListener(\"message\", existing.listener)" in bridge
    assert "existing.announce();" in bridge


def test_connect_failure_is_exposed_without_platform_relogin_prompt():
    """v0.0.0.7 / T03：原名 `test_pairing_supply_unavailable_...`。

    原判据守的是"配对码供应不上时要说清楚，且不要顺手把用户赶去重登平台账号"。
    配对码链路已删，但**那条边界仍然成立**：连不上私人档案馆是一回事，
    平台账号的登录态是另一回事，前者绝不能表现成"你需要重新登录小红书"。
    判据因此重写到新链路上，而不是删掉。
    """
    pwa = PWA.read_text(encoding="utf-8")
    background = (EXT / "background.js").read_text(encoding="utf-8")
    options = (EXT / "options.js").read_text(encoding="utf-8")
    # 连不上时给的是"去档案馆页面登录"，不是"重新登录平台账号"
    assert "请先登录你的档案馆，再连接插件。" in pwa
    assert "还没有连上私人档案馆" in options
    assert "无需输入任何内容" in options
    # 凭据存下来还不算数——必须真的调一次受保护接口验过
    assert "凭据未能通过验证" in background
    # 旧链路的痕迹不许留在这三个文件里
    for text, name in ((pwa, "app.js"), (background, "background.js"), (options, "options.js")):
        assert "pairing_required" not in text, f"{name} 仍在读配对状态"
        assert "one_time_code_available" not in text, f"{name} 仍在读一次性码可用性"


def test_service_worker_uses_persistent_queue():
    """v0.0.0.7 / T03(a)：原名带 `and_scan_heartbeat`。

    心跳端口（sa-account-mirror-scan）是 DOM 抓取器用来汇报滚动进度的，
    随抓取器删除。**持久队列本身与取数方式无关**——它解决的是 MV3 service worker
    随时会被杀掉、同步任务必须能续上，T08 换成 API 拦截之后一样需要它。
    """
    background = (EXT / "background.js").read_text(encoding="utf-8")
    for token in (
        "SYNC_QUEUE_KEY", "SYNC_QUEUE_LOCK_KEY", "enqueueAccountSync",
        "processSyncQueue", "SYNC_QUEUE_ALARM", "already_running",
    ):
        assert token in background


def test_connection_reuses_an_existing_platform_tab_before_opening_a_new_page():
    background = (EXT / "background.js").read_text(encoding="utf-8")
    assert "async function findExistingPlatformTab(platform, preferredTabId = null)" in background
    assert "const existingTab = await findExistingPlatformTab(platform);" in background
    # v0.0.0.22：**不许抢焦点**。Owner 的原话「几个页面乱七八糟的跳来跳去非常乱」，
    # 而这正是他自己定的铁律第 4 条。原来 active: true —— 点一下连接账号，
    # 浏览器当场跳到平台首页，他得自己找回来再点第二次「我已登录，继续」。
    # 复用已有标签页这条不变（这条判据本来守的就是它），改的只是别把人拽过去。
    assert "const tab = existingTab || await chrome.tabs.create({ url: spec.home, active: false });" in background
    assert "await setPendingConnection(platform" in background
    # 原有一条断言此处会注入抓取器脚本。抓取器已删，注入随之取消；
    # **复用已有标签页**这条边界本身与取数方式无关，是 INV-ZERO-BARRIER 的一部分
    # （不要再逼用户登录一次），保留。
    assert "findExistingPlatformTab(platform, pending.tabId)" in background
    assert "插件不会打开新的登录页。" in background


def test_generic_web_label_is_user_facing_chrome_bookmarks_and_web():
    pwa = PWA.read_text(encoding="utf-8")
    assert 'label: "Chrome书签/网页"' in pwa
