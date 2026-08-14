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
    """缓存名与资源戳必须一起升，且 skipWaiting + clients.claim 让新版立刻接管，
    否则回访用户拿到的还是旧 `app.js`。

    实测踩过两次：
    - v0.0.0.7 验 T14 时页面一直显示旧文案，就是这两处还停在 v006；
    - **2026-08-11**：戳的形制是手写的 `v007-r2`，从建站起一次没动过。
      于是 `0.0.0.29` 的「删除并清空」发上生产后，公网那份 `app.js` 仍是
      137559 字节的旧文件（容器里 140335、`cf-cache-status: HIT`、`age: 3794`）。
      **手写的版本，迟早停在某一版。** 现在它等于 `VERSION`，
      由 `scripts/bump_version.py` 每次升版推动。

    这条判据的形制随之改了，**守的东西一个没少**：
    缓存名带版本、三个文件里的戳唯一且一致、SW 立刻接管、没有旧戳残留。
    额外多守一条：戳必须等于当前 `VERSION`——不然「三处一致」可以三处一起旧。
    """
    import re as _re

    index_html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    service_worker = (ROOT / "apps/pwa/sw.js").read_text(encoding="utf-8")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "stamp_pwa_assets_for_sw", ROOT / "scripts/stamp_pwa_assets.py")
    stamper = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(stamper)
    # **戳由内容算，不是版本号。** 跟着版本走会留一扇门：
    # 改了 apps/pwa/ 却忘了升版，戳不动，他还是拿旧的。
    version, _ = stamper.compute_stamp()

    cache_match = _re.search(r'const CACHE = "social-archive-ui-([^"]+)";', service_worker)
    assert cache_match, "sw.js 里找不到带版本的缓存名"
    assert cache_match.group(1) == version, (
        f"SW 缓存名是 {cache_match.group(1)}，而当前版本是 {version}——"
        "名字不换代，老用户那份缓存就永远不换")
    assert "self.skipWaiting()" in service_worker
    assert "self.clients.claim()" in service_worker
    for text, name in ((index_html, "index.html"), (app_js, "app.js"), (service_worker, "sw.js")):
        stamps = set(_re.findall(r"""\?v=([^"'\s>]+)""", text))
        assert stamps, f"{name} 里没有任何带版本的资源引用"
        assert stamps == {version}, (
            f"{name} 的资源戳是 {sorted(stamps)}，当前版本 {version}——"
            "对不上就会出现「缓存换了、资源没换」或反过来")
    assert '"/home"' not in service_worker
    assert "/assets/app.js?v=" in service_worker
    # 旧形制的戳不许残留——留一处就等于那一个资源永远不刷新
    for text in (index_html, app_js, service_worker):
        assert not _re.search(r"\?v=00\d-r\d+", text), "还留着手写的 `00X-rN` 戳"


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
