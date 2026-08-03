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
    assert 'const PRODUCT_VERSION = "0.0.0.6"' in pwa
    assert 'postToExtension("SA_PING", {}, 1500)' in pwa
    assert 'data.type !== "SA_BRIDGE_READY"' in pwa
    assert 'await postToExtension("SA_OPEN_OPTIONS")' in pwa
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
    assert "chrome.tabs.reload" not in background
    assert 'const BRIDGE_STATE_KEY = "__socialArchiveExtensionBridgeState"' in bridge
    assert "window.removeEventListener(\"message\", existing.listener)" in bridge
    assert "existing.announce();" in bridge


def test_pairing_supply_unavailable_is_exposed_without_platform_relogin_prompt():
    pwa = PWA.read_text(encoding="utf-8")
    background = (EXT / "background.js").read_text(encoding="utf-8")
    options = (EXT / "options.js").read_text(encoding="utf-8")
    assert "pairingRequired = pairing?.pairing_required === true" in background
    assert "oneTimeCodeAvailable = pairing?.one_time_code_available === true" in background
    assert "pairingRequired," in background and "oneTimeCodeAvailable," in background
    # The invariant is that a missing pairing supply never steers the Owner into
    # re-logging in to a platform.  The PWA no longer dead-ends on that state at
    # all: having cleared Cloudflare Access it issues the device config itself,
    # so the branch that used to print "已停止配对尝试" is gone by design.
    assert 'api("/v1/pairing/issue"' in pwa
    assert "SA_CONFIGURE" in pwa
    assert "status?.pairing_required === true && !status.one_time_code_available" in options
    assert "等待配对码" in options
    assert "不会请求或改变任一平台的登录状态" in options
    for relogin_prompt in ("重新登录", "请先登录", "重新登陆"):
        assert relogin_prompt not in pwa
        assert relogin_prompt not in options


def test_service_worker_uses_persistent_queue_and_scan_heartbeat():
    background = (EXT / "background.js").read_text(encoding="utf-8")
    content = (EXT / "content/account-mirror.js").read_text(encoding="utf-8")
    for token in (
        "SYNC_QUEUE_KEY", "SYNC_QUEUE_LOCK_KEY", "enqueueAccountSync",
        "processSyncQueue", "SYNC_QUEUE_ALARM", "already_running",
    ):
        assert token in background
    assert 'chrome.runtime.connect({ name: "sa-account-mirror-scan" })' in content
    assert 'port.postMessage({ type: "SA_SCAN_HEARTBEAT"' in content
    assert 'port.name !== "sa-account-mirror-scan"' in background


def test_connection_reuses_an_existing_platform_tab_before_opening_a_new_page():
    background = (EXT / "background.js").read_text(encoding="utf-8")
    assert "async function findExistingPlatformTab(platform, preferredTabId = null)" in background
    assert "const existingTab = await findExistingPlatformTab(platform);" in background
    assert "const tab = existingTab || await chrome.tabs.create({ url: spec.home, active: true });" in background
    assert "await setPendingConnection(platform" in background
    assert "await ensureAccountMirrorScripts(existingTab.id);" in background
    assert "findExistingPlatformTab(platform, pending.tabId)" in background
    assert "插件不会打开新的登录页。" in background


def test_generic_web_label_is_user_facing_chrome_bookmarks_and_web():
    pwa = PWA.read_text(encoding="utf-8")
    assert 'label: "Chrome书签/网页"' in pwa
