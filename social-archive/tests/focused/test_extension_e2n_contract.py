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
        # v0.0.0.7 / T03(a)：两个抓取器文件已删，换成拆分后留下的两半。
        "content/platform-catalog.js", "content/extension-utils.js",
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
    assert {"http://127.0.0.1:8765/*", "http://localhost:8765/*"} <= hosts
    assert all("*://*/*" not in host for host in hosts)
    assert "bookmarks" in manifest.get("optional_permissions", [])
    assert "alarms" in manifest.get("permissions", [])
    # v0.0.0.7 / T06：chrome.cookies 从"全仓禁止"收紧成"只许出现在一个文件里"。
    # 西方三源的取数在服务端跑，需要 cookies.txt；但读 Cookie 的能力必须
    # 关在一个可审计的模块里，不能散进 background/popup/content 任何一处。
    # document.cookie / webRequest / eval 仍然全仓禁止——它们和 T06 无关。
    cookie_readers = sorted(
        str(path.relative_to(root)) for path in root.rglob("*.js")
        if "chrome.cookies" in path.read_text(encoding="utf-8")
    )
    assert cookie_readers == ["cookie-export.js"], (
        f"chrome.cookies 出现在了这些文件里：{cookie_readers}。"
        "读 Cookie 的能力只允许存在于 cookie-export.js 一个模块里。"
    )
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.js"))
    forbidden = ("document.cookie", "webRequest", "eval(", "new Function(")
    assert not any(token in scripts for token in forbidden)
    assert "chrome.permissions.request" in scripts
    assert "Cookie、Token" in (root / "options.html").read_text(encoding="utf-8")


def test_bridge_matches_only_the_documented_web_and_loopback_origins():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    matches = set(manifest["content_scripts"][0]["matches"])
    assert matches == {
        "https://social-archive.linzezhang.com/*",
        "http://127.0.0.1:8765/*",
        "http://localhost:8765/*",
    }
    bridge = (root / "bridge.js").read_text(encoding="utf-8")
    assert '"http://127.0.0.1:8765"' in bridge
    assert '"http://localhost:8765"' in bridge


# v0.0.0.7 / T03(a)：`test_autoscroll_is_isolated_to_explicit_account_mirror_sync`
# 原先断言"只有账号镜像会自动滚页面，其他脚本都不许"。抓取器删掉之后，
# 判据收紧成"**谁都不许滚**"，反转后在
# test_superseded_paths_stay_removed.py::test_extension_never_autoscrolls_any_page。
# 那是更强的判据，不是更弱的。


def test_extension_default_destinations_archive_levels_and_chunk_safe_protocol():
    root = _extension_root()
    shared = (root / "shared.js").read_text(encoding="utf-8")
    background = (root / "background.js").read_text(encoding="utf-8")
    assert '["social_archive", "markdown"]' in shared
    assert '["L0", "L1", "L3"]' in background
    assert 'scope_type: "collection"' in background
    assert 'scope_type: "relation"' in background
    assert "SYNC_QUEUE_KEY" in background and "processSyncQueue" in background
    # 原有一条断言心跳端口 "sa-account-mirror-scan" 存在。那个端口是抓取器
    # 用来汇报滚动进度的，随抓取器删除；持久队列本身与取数方式无关，保留。
