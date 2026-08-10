r"""部署完了，他浏览器里那份 `app.js` 得真的换掉（2026-08-11）。

## 实测到的事故

0.0.0.29 把「删除并清空」按钮发上生产。容器里那份 `app.js` 是 **140335 字节**、
`data-forget-account` 出现 2 次。而从我 Mac 上按普通方式取公网那份：

    $ curl -sI https://social-archive-api.linzezhang.com/assets/app.js
    etag: "1cd51cf082742cf57524b3880a798ce0"
    cf-cache-status: HIT
    age: 3794
    cache-control: max-age=14400

拿到的是 **137559 字节的旧文件**——没有那个按钮。加个 `?t=` 随便什么参数就是新的。

也就是说：**服务端换过了，他刷新最多 4 小时之内拿到的仍是旧代码。**
这是资产层的「出了货没升版＝没出货」——
[[shipping-without-bumping-blinds-the-update-prompt]] 说的是扩展包版本号，
这里是同一个病灶的另一处：`index.html` 里写着

    <script defer src="/assets/app.js?v=007-r2">

`?v=007-r2` 从建站起就没动过。缓存键不变，Cloudflare 当然给旧的。

## 这条判据守什么

1. `index.html` 里每一个 `?v=` 都等于当前版本——不是某个固定的手写串；
2. **升版工具真的会推动它**：拿真 `index.html` 的正文过一遍
   `bump_version.SITES` 里那条规则，看它是不是真换了。
   （只断言「index.html 在 SITES 里」不够——
   [[a-checker-nothing-calls-is-not-a-checker]]：规则写错正则照样是空转。）
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "apps/pwa/index.html"
CACHE_BUSTER = re.compile(r"""\?v=([^"'\s>]+)""")


def _version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _bump_module():
    spec = importlib.util.spec_from_file_location(
        "bump_version_under_test", ROOT / "scripts/bump_version.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_every_cache_buster_is_the_current_version() -> None:
    text = INDEX.read_text(encoding="utf-8")
    stamps = sorted(set(CACHE_BUSTER.findall(text)))
    assert stamps, "首页一个 `?v=` 都没有——那每次部署都靠运气过缓存"
    version = _version()
    assert stamps == [version], (
        f"缓存戳是 {stamps}，而当前版本是 {version}。"
        "对不上就意味着部署完他浏览器里还是旧的——最长 4 小时。")


def test_every_referenced_asset_carries_it() -> None:
    """**首页引的每一个 `/assets/…` 都要带戳。**

    只给 `app.js` 加，改了 CSS 一样发不出去。这里不列白名单——
    以后新增一个资产而忘了加戳，这条要红。

    （第一版我写成 `re.search("app.js")`，撞上第 15 行注释里那句
    「登录后由 app.js 移除」就当成引用了，在正确状态下也报红。
    [[my-checkers-are-mis-cut-six-times-in-one-day]]：模式得对着真文件展开看一眼。）
    """
    text = INDEX.read_text(encoding="utf-8")
    refs = sorted(set(re.findall(r"""(?:src|href)=["'](/assets/[^"']+)""", text)))
    assert len(refs) >= 4, f"首页只引到 {refs}——这条判据的假设过期了"
    version = _version()
    for ref in refs:
        assert ref.endswith(f"?v={version}"), f"{ref} 没带当前版本的缓存戳，它的更新到不了他浏览器"


def test_the_service_worker_precaches_the_urls_the_page_asks_for() -> None:
    """**SW 是第二层缓存。** 它预缓存的 URL 必须就是首页请求的那几个。

    原来首页请求 `/assets/app.js?v=0.0.0.30`，而 sw.js 里存的是 `?v=007-r2`
    ——两个不同的缓存键，预存的那份没人会用到，而且缓存名不换代，
    回访用户手里那份永远不换。
    """
    version = _version()
    sw = (ROOT / "apps/pwa/sw.js").read_text(encoding="utf-8")
    precached = set(re.findall(r'"(/assets/[^"]+)"', sw))
    referenced = set(re.findall(
        r"""(?:src|href)=["'](/assets/[^"']+)""", INDEX.read_text(encoding="utf-8")))
    missing = referenced - precached
    assert not missing, f"首页要这几个而 SW 没预存（键对不上）：{sorted(missing)}"
    assert f'social-archive-ui-{version}"' in sw, "SW 缓存名没跟着版本换代"


def test_the_deploy_really_calls_the_real_chrome_drill() -> None:
    """**没有调用方的判据不算判据。**（[[a-checker-nothing-calls-is-not-a-checker]]）

    源码层三道门都绿的那天，公网仍在下发没有这颗按钮的旧 `app.js`。
    真正能戳穿它的只有「从公开域名取前端 → 喂真 Chrome → 读 DOM」，
    所以部署脚本必须每次都跑它，且它红了要**中止部署**——
    不能只打印一行然后继续。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    for drill, why in (
        ("forget_button_render_drill.py", "真 Chrome 里验这次发的界面到不到得了他手上"),
        ("from_zero_drill.py", "在刚部署的镜像上把「从零到能用」这条链真走一遍"),
    ):
        assert drill in deploy, f"部署脚本没有调用 {drill}——{why}，它就成了没人跑的摆设"
        step = deploy[deploy.index(drill):]
        step = step[:step.index('step "9)')]
        assert "fail " in step, f"{drill} 红了不中止部署，等于没验"
        assert "| tail" not in step and "| head" not in step, (
            f"{drill} 的成败别接进管道——`fail` 会读到管道尾巴那条命令的退出码")
        assert (ROOT / "scripts" / drill).is_file()


def test_the_bump_tool_actually_moves_every_stamp() -> None:
    """**真跑那些规则。** 不是「文件在清单里」，是它们换得动。

    覆盖三个承重位：首页的戳、SW 的缓存名与预缓存清单、app.js 里注册 SW 的 URL。
    """
    module = _bump_module()
    old = _version()
    targets = {
        "apps/pwa/index.html": INDEX,
        "apps/pwa/sw.js": ROOT / "apps/pwa/sw.js",
        "apps/pwa/app.js": ROOT / "apps/pwa/app.js",
    }
    for name, path in targets.items():
        rules = [site for site in module.SITES if site[0] == name]
        assert rules, f"升版工具不再管 {name} 了——那里的戳又会漂回一个不动的常量"
        text = path.read_text(encoding="utf-8")
        for _n, pattern, replacement, _why in rules:
            compiled = re.compile(pattern.replace("{old}", re.escape(old)))
            assert compiled.findall(text), f"{name} 的规则 {pattern!r} 一处都匹配不到"
            text = compiled.sub(replacement.replace("{new}", "9.9.9.9"), text)
        left = sorted(set(CACHE_BUSTER.findall(text)))
        assert left in ([], ["9.9.9.9"]), f"{name} 升版后还留着旧戳：{left}"
        if name != "apps/pwa/app.js":  # app.js 里还有别的地方会提到版本号
            assert old not in text, f"{name} 升完版还留着旧版本号"
    sw_bumped = re.sub(
        r'social-archive-ui-' + re.escape(old), "social-archive-ui-9.9.9.9",
        (ROOT / "apps/pwa/sw.js").read_text(encoding="utf-8"))
    assert "social-archive-ui-9.9.9.9" in sw_bumped
