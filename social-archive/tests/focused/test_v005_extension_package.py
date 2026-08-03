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


def test_service_worker_replaces_the_stale_v005_ui_cache_with_v006_assets_immediately():
    index_html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    service_worker = (ROOT / "apps/pwa/sw.js").read_text(encoding="utf-8")
    assert 'const CACHE = "social-archive-ui-v006-r1";' in service_worker
    assert "self.skipWaiting()" in service_worker
    assert "self.clients.claim()" in service_worker
    assert 'href="/assets/styles.css?v=006-r1"' in index_html
    assert 'src="/assets/app.js?v=006-r1"' in index_html
    assert 'register("/assets/sw.js?v=006-r1")' in app_js
    assert '"/home"' not in service_worker
    assert '"/assets/app.js?v=006-r1"' in service_worker


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
