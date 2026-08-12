r"""部署完了，他浏览器里那份 `app.js` 得真的换掉（2026-08-11）。

## 实测到的事故

0.0.0.29 把「删除并清空」按钮发上生产。容器里那份 `app.js` 是 **140335 字节**、
`data-forget-account` 出现 2 次。而从我 Mac 上按普通方式取公网那份：

    content-length: 137559     ← 少了 2776 字节，**里面没有那颗按钮**
    cf-cache-status: HIT
    age: 3794
    cache-control: max-age=14400

服务端换过了，他刷新最多 4 小时之内仍是旧代码——资产层的「出了货没升版＝没出货」。

## 为什么源站设 Cache-Control 治不了（同日实测）

    源站（生产机上打回环 127.0.0.1:18765）  HTTP/1.1 200 OK   ← 一个 cache-control 都没有
    公网（经 Cloudflare）                   cache-control: max-age=14400

**那 4 小时是 Cloudflare 的 Browser Cache TTL 加的**，源站的头会被它盖掉
（另一个会话在自己的 zone 上量到源站 `no-cache` 同样被覆盖）。
所以**换缓存键是唯一可靠的手段**，而键必须永远正确、不能靠人记得。

## 戳为什么是内容派生的，不是跟着版本号

第一版跟着 `VERSION` 走。那修好了「戳永远不动」，却留下同形状的后门：
**改了 `apps/pwa/` 却忘了升版** → 戳不动 → 他还是拿旧的。
（`apps/browser-extension/` 有「改了就必须升版」那条判据，`apps/pwa/` 没有。）

现在 `scripts/stamp_pwa_assets.py` 按内容算 `sha256[:8]`：改了内容哈希必变，
忘不掉也糊弄不了。

## 这条判据守什么

1. 首页引的**每一个** `/assets/…` 都带戳，且戳等于按内容现算的那个（不列白名单）；
2. SW 预缓存的键就是首页请求的键，缓存名同一个戳；
3. 打戳脚本**收敛**（跑两次结果一样）——不收敛的话每次部署都在换键，等于没缓存；
4. 部署真的会跑 `--check`，红了中止。
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "apps/pwa/index.html"
SW = ROOT / "apps/pwa/sw.js"
CACHE_BUSTER = re.compile(r"""\?v=([^"'\s>)]*)""")


def _stamper():
    spec = importlib.util.spec_from_file_location(
        "stamp_pwa_assets_under_test", ROOT / "scripts/stamp_pwa_assets.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_every_cache_buster_equals_the_content_hash() -> None:
    stamp, hashed = _stamper().compute_stamp()
    assert len(hashed) >= 5, f"只哈希到 {hashed}——漏了资产就等于那几个永远不刷新"
    stamps = sorted(set(CACHE_BUSTER.findall(INDEX.read_text(encoding="utf-8"))))
    assert stamps, "首页一个 `?v=` 都没有——那每次部署都靠运气过缓存"
    assert stamps == [stamp], (
        f"缓存戳是 {stamps}，而按内容现算是 {stamp}。"
        "对不上就意味着部署完他浏览器里还是旧的——最长 4 小时。"
        "改完资产要跑一次 scripts/stamp_pwa_assets.py")


def test_every_referenced_asset_carries_it() -> None:
    """**首页引的每一个 `/assets/…` 都要带戳。** 不列白名单——
    以后新增一个资产而忘了加戳，这条要红。"""
    stamp, _ = _stamper().compute_stamp()
    refs = sorted(set(re.findall(
        r"""(?:src|href)=["'](/assets/[^"']+)""", INDEX.read_text(encoding="utf-8"))))
    assert len(refs) >= 4, f"首页只引到 {refs}——这条判据的假设过期了"
    for ref in refs:
        assert ref.endswith(f"?v={stamp}"), f"{ref} 没带当前内容的戳，它的更新到不了他浏览器"


def test_the_service_worker_precaches_the_urls_the_page_asks_for() -> None:
    """**SW 是第二层缓存。** 它预缓存的 URL 必须就是首页请求的那几个。"""
    stamp, _ = _stamper().compute_stamp()
    sw = SW.read_text(encoding="utf-8")
    precached = set(re.findall(r'"(/assets/[^"]+)"', sw))
    referenced = set(re.findall(
        r"""(?:src|href)=["'](/assets/[^"']+)""", INDEX.read_text(encoding="utf-8")))
    missing = referenced - precached
    assert not missing, f"首页要这几个而 SW 没预存（键对不上）：{sorted(missing)}"
    assert f'social-archive-ui-{stamp}"' in sw, "SW 缓存名没跟着内容换代"


def test_the_stamper_converges() -> None:
    """**跑两次结果一样。** 不收敛的话每次部署都换键，等于把缓存整个关掉。

    收敛靠的是：哈希之前先把所有 `?v=…` 归一成 `?v=`
    （`app.js` 里写着 SW 的地址、`sw.js` 里写着预缓存清单，它们本身都含戳）。
    """
    module = _stamper()
    first, _ = module.compute_stamp()
    second, _ = module.compute_stamp()
    assert first == second
    done = subprocess.run([sys.executable, str(ROOT / "scripts/stamp_pwa_assets.py"), "--check"],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout[-800:]


def test_the_deploy_really_calls_the_real_chrome_drill() -> None:
    """**没有调用方的判据不算判据。**

    源码层三道门都绿的那天，公网仍在下发没有那颗按钮的旧 `app.js`。
    真正能戳穿它的只有「从公开域名取前端 → 喂真 Chrome → 读 DOM」，
    所以部署必须每次都跑它，且红了要**中止部署**。
    打戳的 `--check` 同理：漏跑一次就等于这一版发不出去。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    for drill, why in (
        ("forget_button_render_drill.py", "真 Chrome 里验这次发的界面到不到得了他手上"),
        ("from_zero_drill.py", "在刚部署的镜像上把「从零到能用」这条链真走一遍"),
        ("stamp_pwa_assets.py", "戳和内容对不上就等于这一版到不了他浏览器"),
    ):
        assert drill in deploy, f"部署脚本没有调用 {drill}——{why}，它就成了没人跑的摆设"
        # **切到「下一个 step」为止**，不是切到 step 9。
        # 第一版切到 `step "9)"`，而打戳那一步在第 0.5 步——中间夹着七八个别的
        # 步骤，`| tail` 之类当然会命中，判据于是对着一段不属于它的脚本报红。
        # （`my-checkers-are-mis-cut-six-times-in-one-day`：窗口够不到要守的东西。）
        step = deploy[deploy.index(drill):]
        nxt = step.find('\nstep "')
        step = step[:nxt] if nxt > 0 else step
        assert "fail " in step, f"{drill} 红了不中止部署，等于没验"
        assert "| tail" not in step and "| head" not in step, (
            f"{drill} 的成败别接进管道——`fail` 会读到管道尾巴那条命令的退出码")
        assert (ROOT / "scripts" / drill).is_file()
