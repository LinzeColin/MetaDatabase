from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def test_extension_has_no_cookie_permission_and_no_autoscroll():
    text=(ROOT/'apps/browser-extension/manifest.json').read_text(encoding='utf-8');assert '"cookies"' not in text and 'webRequest' not in text
    js=(ROOT/'apps/browser-extension/sidepanel.js').read_text(encoding='utf-8');assert 'scrollTo(' not in js and 'scrollBy(' not in js


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
