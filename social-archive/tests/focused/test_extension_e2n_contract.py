import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _extension_root() -> Path:
    return Path(__file__).parents[2] / "apps/browser-extension"


def test_extension_has_account_mirror_first_surfaces():
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
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
    # v0.0.0.22：原来钉的是带「点赞」的那句。那句在超售——一个平台都没有同步点赞。
    # **逐字钉文案的判据会把当时的错一起钉牢**：这句超售了多少版，它就替它挡了多少版。
    assert "连接一次账号，收藏和书签自动搬进来" in options
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


def _war(manifest: dict) -> dict:
    """连接面板那一条 web_accessible_resources。"""
    for entry in manifest.get("web_accessible_resources", []):
        if "connect-frame.html" in entry.get("resources", []):
            return entry
    raise AssertionError(
        "manifest 里没有一条 web_accessible_resources 放行 connect-frame.html——"
        "那么资料库上的「连接账号」点开只会是一个空白面板")


def test_the_connect_frame_is_reachable_from_every_page_the_bridge_runs_on():
    """**bridge 跑到哪一页，连接面板就必须能在那一页嵌得起来。**

    2026-08-07 改坏测试查出来的：把生产域名从 `web_accessible_resources.matches`
    里删掉，**1198 条测试全过、31 道门全绿**。另外两处（content_scripts、
    host_permissions）都有人管，只有这一处没有。

    后果不是「少了个功能」，是**他点的那颗按钮打开一个空白面板**：
    `bridge.js` 把 `chrome.runtime.getURL("connect-frame.html")` 递给页面，
    `app.js:openConnectPanel` 把它塞进 iframe 的 src。域名不在 WAR 里，
    Chrome 直接拦掉这个子框架——而 `openConnectPanel` 只看 url 和元素在不在，
    照样 `return true`，代码这一侧一点声音都没有。

    而 `localhost:8765` 一直在名单里，所以**17 个演练全跑在能用的那一侧**，
    死的只有 Owner 那一侧。这正是「只在作者机器上是好的」那一类。

    **不再抄第四份域名清单**——抄的清单下次加域名照样漏。这里钉的是关系：
    bridge 的 matches ⊆ 连接面板的 matches。往 content_scripts 加一个域名而
    忘了 WAR，这条当场红。
    """
    manifest = json.loads((_extension_root() / "manifest.json").read_text(encoding="utf-8"))
    bridge_origins = {m for cs in manifest["content_scripts"] for m in cs["matches"]}
    assert bridge_origins, "一个 content_scripts.matches 都没读到——这条判据在空扫"
    reachable = set(_war(manifest).get("matches", []))
    missing = sorted(bridge_origins - reachable)
    assert not missing, (
        f"bridge 会在这些页面上跑，而连接面板嵌不进去：{missing}\n"
        "他点「连接账号」会看到一个空白面板，而不是任何错误提示。\n"
        "把它们加进 manifest 的 web_accessible_resources.matches。")


def test_everything_the_connect_frame_loads_is_web_accessible():
    """面板嵌得进来还不够——**它自己要加载的东西也得放行**。

    connect-frame.html 里少放行一个 `<script src>`，面板一样是空白的：
    框架加载成功，脚本被拦，一颗按钮都画不出来。所以从 HTML 里现读它引用了
    什么，而不是照着 resources 那张表复述一遍。
    """
    root = _extension_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    html = (root / "connect-frame.html").read_text(encoding="utf-8")
    referenced = {
        ref for ref in re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', html)
        if not ref.startswith(("http://", "https://", "data:", "#"))
    }
    assert referenced, "connect-frame.html 里一个本地引用都没读到——这条判据在空扫"
    allowed = set(_war(manifest).get("resources", []))
    missing = sorted(ref.lstrip("./") for ref in referenced if ref.lstrip("./") not in allowed)
    assert not missing, (
        f"连接面板要加载这些文件，而它们没被放行：{missing}\n"
        "面板会加载出来但画不出按钮——他看到的是一个空白框。")


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
