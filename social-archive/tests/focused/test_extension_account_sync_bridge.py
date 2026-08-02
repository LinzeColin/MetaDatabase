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


def test_generic_web_label_is_user_facing_chrome_bookmarks_and_web():
    pwa = PWA.read_text(encoding="utf-8")
    assert 'label: "Chrome书签/网页"' in pwa
