from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_pwa_has_core_views_and_chinese_labels():
    html=(ROOT/'apps/pwa/index.html').read_text(encoding='utf-8');js=(ROOT/'apps/pwa/app.js').read_text(encoding='utf-8')
    for text in ('所有收藏，一个入口','平台状态','新手向导'):assert text in html
    for endpoint in ('/v1/library','/v1/connectors','/v1/storage/status'):assert endpoint in js
