"""PWA 的核心入口与中文标签（v0.0.0.4 起，v0.0.0.7 逐条重核）。

## 这条判据红了很久，逐条查完是四种不同的情况

原来它断言 index.html 里有「资料库 / 连接中心 / 三步开始」，
app.js 里有「/v1/library / /v1/extension/bootstrap / /v1/storage/status」。

    资料库                    ✓ 一直有
    连接中心                  **陈旧**：v0.0.0.6（40d833bf）改名为「账号同步中心」，
                              而 docs 手册没跟着改 —— 是文档和判据同时落后于界面
    三步开始                  **陈旧**：同一次 overlay 里删掉了这个引导元素
    /v1/library               ✓ 一直有
    /v1/extension/bootstrap   **指错对象**：那是**扩展**的端点，
                              popup.js / background.js / options.js 在调。
                              PWA 没有理由调它。
    /v1/storage/status        **真缺口**：服务端算得出配额、还自带 message_zh，
                              而 PWA 一次都没调过 —— v0.0.0.7 已接上

判「陈旧」不是靠猜：`git log -S` 查出「连接中心」是 v0.0.0.5（2026-08-02）
进手册的，「账号同步中心」是 v0.0.0.6（2026-08-03）进界面的，
而手册自 08-02 起没再动过。**界面是新的，手册和判据是旧的。**
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pwa_has_core_views_and_chinese_labels():
    html = (ROOT / 'apps/pwa/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'apps/pwa/app.js').read_text(encoding='utf-8')

    # 用户进得去的两个核心入口。名字用**界面当前的**说法，
    # 不用手册里那个 v0.0.0.5 的旧词。
    for text in ('资料库', '账号同步中心'):
        assert text in html, f'PWA 少了核心入口：{text}'

    # 「授权平台」这件事必须在那个入口里做得到——判的是能力，不是标题文字
    for control in ('连接新账号', '连接状态'):
        assert control in html, f'账号同步中心里缺少「{control}」，那就不是连接入口了'

    # PWA 自己该调的接口。extension/bootstrap **不在此列**：那是扩展的。
    for endpoint in ('/v1/library', '/v1/storage/status'):
        assert endpoint in js, f'PWA 没有调用 {endpoint}'


def test_extension_bootstrap_belongs_to_the_extension_not_the_pwa():
    """把「谁该调它」钉住，免得日后又被写回 PWA 的判据里。"""
    ext = ROOT / 'apps/browser-extension'
    callers = [p.name for p in ext.glob('*.js')
               if '/v1/extension/bootstrap' in p.read_text(encoding='utf-8')]
    assert callers, '扩展自己反而不调 /v1/extension/bootstrap 了'
    pwa_js = (ROOT / 'apps/pwa/app.js').read_text(encoding='utf-8')
    assert '/v1/extension/bootstrap' not in pwa_js, (
        'PWA 调了扩展专用的 bootstrap 接口——两边的引导流程不该混在一起'
    )
