from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_pwa_has_core_views_and_chinese_labels():
    html=(ROOT/'apps/pwa/index.html').read_text(encoding='utf-8');js=(ROOT/'apps/pwa/app.js').read_text(encoding='utf-8')
    for text in ('资料库','连接中心','三步开始'):assert text in html
    for endpoint in ('/v1/library','/v1/extension/bootstrap','/v1/storage/status'):assert endpoint in js
