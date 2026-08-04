from pathlib import Path
import json
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def test_extension_package_builds_and_contains_installable_root():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/build_extension_package.py")], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    archive = Path(payload["output"])
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "popup.html", "background.js", "bridge.js", "content/extract-core.js"} <= names
        assert not any(name.startswith("browser-extension/") for name in names)


def test_floating_save_uses_the_message_sender_tab_without_active_tab_races():
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "async function captureActive(message = {}, sourceTab = null)" in background
    assert "sourceTab?.id && sourceTab?.url ? sourceTab : await SA.activeTab()" in background
    assert "onMessage.addListener((message, sender, sendResponse)" in background
    assert 'captureActive(message, sender?.tab)' in background


def test_pwa_routes_uninstalled_users_through_the_chinese_install_guide():
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    guide = (ROOT / "apps/pwa/extension-install.html").read_text(encoding="utf-8")
    assert 'location.href = "/extension-install"' in app_js
    assert "/downloads/social-archive-extension.zip" in guide
    for instruction in ("双击解压", "chrome://extensions", "开发者模式", "加载已解压的扩展程序", "点击连接"):
        assert instruction in guide


def test_service_worker_replaces_the_stale_ui_cache_with_current_assets_immediately():
    """v0.0.0.7：版本号从 006 移到 007。**守的原则没变**——

    缓存名与资源版本号必须随界面改动一起升，且 skipWaiting + clients.claim
    要让新版立刻接管，否则回访用户拿到的还是旧 app.js。

    本轮实测踩到过：验 T14 时页面一直显示旧文案，就是这两处还停在 v006。
    发布后老用户会完全看不到 v0.0.0.7 的界面改动——这是发布级问题，不是小事。
    """
    index_html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    service_worker = (ROOT / "apps/pwa/sw.js").read_text(encoding="utf-8")
    # **不逐字钉死版本号。** 这个值本来就必须随每次界面改动而变，
    # 钉死它只能证明「没人动过它」——而「没人动它」正是这条判据要防的那个 bug。
    # （实测：补登录闸时把 r1 顶成 r2，这条判据反而报红。）
    # 改成断言四处**互相一致**：缓存名、三处 ?v= 查询串必须是同一个版本。
    import re as _re

    cache_match = _re.search(r'const CACHE = "social-archive-ui-(v\d+-r\d+)";', service_worker)
    assert cache_match, "sw.js 里找不到带版本的缓存名"
    tag = cache_match.group(1).split("-", 1)[1]  # v007-r2 → r2
    version = cache_match.group(1).replace("v0", "0").replace("-", "-")  # 仅用于报错信息
    assert "self.skipWaiting()" in service_worker
    assert "self.clients.claim()" in service_worker
    for text, name in ((index_html, "index.html"), (app_js, "app.js"), (service_worker, "sw.js")):
        stamps = set(_re.findall(r"\?v=(00\d-r\d+)", text))
        assert stamps, f"{name} 里没有任何带版本的资源引用"
        assert len(stamps) == 1, f"{name} 里混着多个版本戳 {sorted(stamps)}——总有一个资源不会刷新"
        assert stamps.pop().endswith(tag), (
            f"{name} 的资源版本戳与 sw.js 的缓存名（{cache_match.group(1)}）不一致，"
            "会出现「缓存换了、资源没换」或反过来"
        )
    assert '"/home"' not in service_worker
    assert "/assets/app.js?v=" in service_worker
    # 旧版本号不许残留在任何一处——留一处就等于那一个资源永远不刷新
    for text in (index_html, app_js, service_worker):
        assert "v=006" not in text and "v005" not in text


def test_core_image_includes_only_the_fixed_extension_package():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")

    assert "SOCIAL_ARCHIVE_EXTENSION_PACKAGE=/app/dist/social-archive-extension.zip" in dockerfile
    assert "RUN python3 scripts/build_extension_package.py" in dockerfile
    assert "COPY dist/social-archive-extension.zip ./dist/social-archive-extension.zip" not in dockerfile
    assert "dist/*" in dockerignore
    assert "!dist/social-archive-extension.zip" not in dockerignore


def test_install_rebuilds_the_host_package_before_the_container_build():
    install = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    assert "scripts/build_extension_package.py" in install
    assert install.index('"$PYTHON" scripts/build_extension_package.py') < install.index("docker compose build core-api core-worker cli-tools")
