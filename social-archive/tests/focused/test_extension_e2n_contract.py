import json
from pathlib import Path


def _extension_root() -> Path:
    return Path(__file__).parents[2] / "apps/browser-extension"


def test_extension_has_account_mirror_first_surfaces():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["version"] == "0.0.0.6"
    assert manifest["action"]["default_popup"] == "popup.html"
    assert manifest["side_panel"]["default_path"] == "sidepanel.html"
    assert manifest["options_page"] == "options.html"
    required = {
        "popup.html", "popup.js", "popup.css", "sidepanel.html", "sidepanel.js",
        "options.html", "options.js", "options.css", "shared.js", "background.js",
        "content/fab.js", "content/extract.js", "content/extract-core.js",
        "content/account-mirror.js", "content/account-mirror-core.js",
        "bridge.js", "runtime-config.json",
    }
    assert required <= {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
    text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*.js"))
    for phrase in (
        "SA_ACCOUNT_CONNECT", "SA_SYNC_ACCOUNT", "SA_SYNC_ALL_ACCOUNTS",
        "flattenBookmarksTree", "syncChromeBookmarks", "destinationIds", "needs_user_action",
    ):
        assert phrase in text
    options = (root / "options.html").read_text(encoding="utf-8")
    assert "连接一次账号，收藏、点赞和书签自动搬进来" in options
    assert "立即同步全部账号" in options


def test_extension_auth_and_privacy_boundaries_are_explicit():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert "<all_urls>" not in manifest.get("host_permissions", [])
    hosts = set(manifest["host_permissions"])
    assert "https://social-archive-api.linzezhang.com/*" in hosts
    assert "https://social-archive.linzezhang.com/*" in hosts
    assert all("*://*/*" not in host for host in hosts)
    assert "bookmarks" in manifest.get("optional_permissions", [])
    assert "alarms" in manifest.get("permissions", [])
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.js"))
    forbidden = ("document.cookie", "chrome.cookies", "webRequest", "eval(", "new Function(")
    assert not any(token in scripts for token in forbidden)
    assert "chrome.permissions.request" in scripts
    assert "Cookie、Token" in (root / "options.html").read_text(encoding="utf-8")


def test_autoscroll_is_isolated_to_explicit_account_mirror_sync():
    root = _extension_root()
    mirror = (root / "content/account-mirror.js").read_text(encoding="utf-8")
    assert "scrollTo(" in mirror
    assert "SA_MIRROR_SCAN_RELATION" in mirror
    for relative in ("content/extract.js", "content/fab.js", "popup.js", "sidepanel.js", "options.js"):
        text = (root / relative).read_text(encoding="utf-8")
        assert "scrollTo(" not in text and "scrollBy(" not in text


def test_extension_default_destinations_archive_levels_and_chunk_safe_protocol():
    root = _extension_root()
    shared = (root / "shared.js").read_text(encoding="utf-8")
    background = (root / "background.js").read_text(encoding="utf-8")
    assert '["social_archive", "markdown"]' in shared
    assert '["L0", "L1", "L3"]' in background
    assert 'scope_type: "collection"' in background
    assert 'scope_type: "relation"' in background
    assert "SYNC_QUEUE_KEY" in background and "processSyncQueue" in background
    assert "sa-account-mirror-scan" in background
