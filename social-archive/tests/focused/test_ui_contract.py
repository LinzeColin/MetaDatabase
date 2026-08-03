from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def test_extension_cookie_permission_is_optional_only_and_no_autoscroll():
    """v0.0.0.7 / T06：原名 `test_extension_has_no_cookie_permission_...`。

    v0.0.0.6 的边界是「扩展完全不碰 Cookie」。T06 有意改变它——西方三源要在
    服务端跑 gallery-dl / yt-dlp，得有一份 cookies.txt。

    **判据没有被删掉，是被收紧成更具体的形状**：
      · cookies 只能是**可选**权限，装插件时不申请
      · webRequest 仍然一律禁止（那是能看到所有流量的权限，T06 用不到）
    直接删掉这条会把「不许常驻申请 Cookie 权限」这条边界一起丢了。
    """
    import json as _json
    manifest = _json.loads((ROOT / 'apps/browser-extension/manifest.json').read_text(encoding='utf-8'))
    assert 'cookies' not in manifest.get('permissions', []), '扩展不该常驻申请 Cookie 权限'
    assert 'cookies' in manifest.get('optional_permissions', [])
    assert 'webRequest' not in _json.dumps(manifest), 'webRequest 能看到全部流量，本产品用不到'
    js = (ROOT / 'apps/browser-extension/sidepanel.js').read_text(encoding='utf-8')
    assert 'scrollTo(' not in js and 'scrollBy(' not in js


def test_pwa_unified_library_has_feed_grid_detail_and_responsive_contract():
    html = (ROOT / 'apps/pwa/index.html').read_text(encoding='utf-8')
    app = (ROOT / 'apps/pwa/app.js').read_text(encoding='utf-8')
    styles = (ROOT / 'apps/pwa/styles.css').read_text(encoding='utf-8')
    assert 'id="library"' in html
    assert 'data-view="feed"' in html
    assert 'data-view="grid"' in html
    assert 'id="detailDialog"' in html and 'id="detailContent"' in html
    assert 'id="collectionFilter"' in html and 'id="observedFrom"' in html and 'id="observedTo"' in html
    assert 'href="/assets/favicon.svg"' in html
    assert '/v1/library?' in app and 'openDetail' in app
    assert 'const relationPills = relations.length' in app
    assert "const relationHistory = relations.length" in app
    assert "params.set('collection', collection)" in app and "params.set('observed_from', observedFrom)" in app
    assert '.library.feed' in styles and '.library.grid' in styles
    assert '.relation-history' in styles and '.filter-date-range' in styles
    assert '@media(max-width:900px)' in styles and '@media(max-width:600px)' in styles
