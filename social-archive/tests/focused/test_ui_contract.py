import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
    """资料库要能浏览、筛选、看详情，并且在窄屏可用。

    **这条判据按能力重写过一次（v0.0.0.7），原因记在这里。**

    原来它钉的是 v0.0.0.5 的那套标记：id="library"、data-view="feed"/"grid"、
    id="detailDialog"、.library.feed/.library.grid、@media(max-width:900px)…
    v0.0.0.6 的 SA-003 overlay（40d833bf）**把整套界面换掉了**：
    卡片流/网格 → 一张可排序可分页的表；对话框 → 抽屉；断点 900/600 → 1180/760。

    能力一个没少（真实浏览器实测：12 列表格、62 条分两页、抽屉详情、
    收藏夹/关系/主题/日期筛选都在），少的只是那批旧标记。
    所以现在钉**能力**：有表体、有详情载体、有筛选、有断点。
    钉具体 id 的代价就是上面那样——界面一改版，判据全红，
    而红的原因和「界面坏没坏」无关。
    """
    html = (ROOT / 'apps/pwa/index.html').read_text(encoding='utf-8')
    app = (ROOT / 'apps/pwa/app.js').read_text(encoding='utf-8')
    styles = (ROOT / 'apps/pwa/styles.css').read_text(encoding='utf-8')

    # 浏览：一张表，表体由 app.js 填
    assert 'id="tableBody"' in html, '资料库没有表体容器'
    # 详情：抽屉（v0.0.0.6 起取代 dialog）
    assert 'id="detailDrawer"' in html and 'id="drawerContent"' in html, '没有详情载体'
    # 筛选：至少要有关系/主题/日期这几维
    for control in ('relationFilter', 'topicFilter', 'dateFilter'):
        assert f'id="{control}"' in html, f'资料库缺少筛选控件 {control}'
    # 2026-08-11：favicon 也带上了 `?v=<版本>` 的缓存戳，所以这里只钉「有这个图标」。
    # 戳本身由 test_the_browser_gets_the_new_front_end.py 单独守着
    # （每个 /assets 引用都必须带、且等于当前版本）——那条才是防「发了到不了他浏览器」的。
    assert 'href="/assets/favicon.svg' in html

    # 数据来源与详情入口
    assert '/v1/library?' in app and 'openDetail' in app

    # 窄屏可用：断点写法可以变，**有没有断点不能变**
    breakpoints = re.findall(r'@media\s*\(\s*max-width', styles)
    assert len(breakpoints) >= 2, f'响应式断点不足（找到 {len(breakpoints)} 个）'
