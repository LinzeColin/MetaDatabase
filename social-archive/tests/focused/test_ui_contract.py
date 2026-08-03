import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_extension_has_no_cookie_or_network_interception_permission():
    manifest = json.loads((ROOT / "apps/browser-extension/manifest.json").read_text(encoding="utf-8"))
    permissions = set(manifest.get("permissions", [])) | set(manifest.get("optional_permissions", []))
    assert "cookies" not in permissions
    assert "webRequest" not in permissions
    assert "webRequestBlocking" not in permissions


def test_account_mirror_is_primary_and_single_page_capture_is_fallback():
    popup = (ROOT / "apps/browser-extension/popup.html").read_text(encoding="utf-8")
    options = (ROOT / "apps/browser-extension/options.html").read_text(encoding="utf-8")
    assert "同步全部已连接账号" in popup
    assert "备用" in popup
    assert "连接一次账号" in options
    assert "不需要逐条打开帖子" in options


def test_extension_side_panel_never_autoscrolls_the_page():
    # Preserved from the pre-reconcile upstream copy: scrolling the user's page
    # is how a reader turns into a crawler, so keep it out of the side panel.
    js = (ROOT / "apps/browser-extension/sidepanel.js").read_text(encoding="utf-8")
    assert "scrollTo(" not in js and "scrollBy(" not in js


def test_pwa_table_shell_stays_responsive_and_respects_reduced_motion():
    # The v0.0.0.5 assertion named .library.feed/.library.grid and
    # @media(max-width:900px); the Owner-approved table shell replaced those
    # views entirely, so bind the breakpoints the current shell actually ships.
    styles = (ROOT / "apps/pwa/styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 1180px)" in styles
    assert "@media (max-width: 760px)" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
