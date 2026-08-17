r"""扩展要去的那个资料库地址，必须真的配得上（2026-08-17）。

## 它修的是什么

Owner 报「不断跳转没用的页面、永远连接不了、永远不能同步」。根因是三处不一致：

    runtime-config.library_url        https://social-archive.linzezhang.com
    manifest content_scripts.matches  https://social-archive.linzezhang.com/*  ← 只有它
    bridge.js allowedOrigins          https://social-archive.linzezhang.com    ← 只有它

而那个域名在 Cloudflare Access 后面（实测 `/` 302 到登录页）。于是两条路都堵死：

· 开被挡的域名 → 页面根本没加载 → bridge 没注入 → 配不上
· 开接口域名（**同一份前端，没有墙**）→ 不在 matches / allowedOrigins 里 → 一样配不上

结果 `/v1/*` 永远 401「扩展尚未授权或令牌已失效」，界面永远转圈，
而 `library_url` 又一直把人往那堵墙上送——就是他说的那三句话。

## 为什么十四个真 Chrome 演练全绿

它们**每一个**都带 `--host-resolver-rules=MAP social-archive.linzezhang.com 127.0.0.1:<假端口>`。
域名被指到本机假服务器上，**结构上撞不到那堵墙**。
`evidence/T03/FIRST_RUN_DETECTION_ACTUALLY_WORKS.json` 里我自己写着：
「他用的是 https://social-archive.linzezhang.com——同一条 manifest 规则，
**但没有在那个来源上实测过**（那需要他的 Cloudflare Access 会话）」。
缺口记下了，从没堵上，然后它咬了他三个星期。

## 这道判据守的不变量

**扩展要送用户去的那个来源，必须同时在两张名单里。** 少一张就配不上，
而两张名单在两个文件里，改一处不改另一处不会有任何报错——正是这次的形状。

（能不能打开是网络的事，交给 `check_the_guide_warns_about_the_access_gate.py`
去真打一次；这里只钉离线就能钉死的那一半，好让它在没有网络的环境里也拦得住。）
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"


def _library_origin() -> str:
    config = json.loads((EXT / "runtime-config.json").read_text(encoding="utf-8"))
    url = str(config.get("library_url") or "")
    assert url, "runtime-config.json 里没有 library_url——扩展不知道该把人送去哪"
    parsed = urlparse(url)
    assert parsed.scheme and parsed.netloc, f"library_url 不是个地址：{url!r}"
    return f"{parsed.scheme}://{parsed.netloc}"


def _manifest_bridge_matches() -> list[str]:
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest.get("content_scripts") or []:
        if "bridge.js" in (entry.get("js") or []):
            return list(entry.get("matches") or [])
    raise AssertionError(
        "manifest 里没有任何一条 content_script 注入 bridge.js——"
        "配对那根线整个没了，比域名对不上更严重")


def _bridge_allowed_origins() -> set[str]:
    """从 bridge.js 里把 allowedOrigins 那个集合读出来。

    **不 import、不执行**，用正则切那一段字面量：这个文件是浏览器脚本，
    在 pytest 里跑不起来。切出来之后下面会断言它非空——
    正则失效时必须红，不能变成「读到空集合所以随便什么都算在里面」。
    """
    source = (EXT / "bridge.js").read_text(encoding="utf-8")
    block = re.search(r"allowedOrigins\s*=\s*new Set\(\s*\[(.*?)\]", source, re.S)
    assert block, "bridge.js 里找不到 allowedOrigins——改名了就把这条一起改"
    origins = set(re.findall(r'["\']([^"\']+)["\']', block.group(1)))
    assert origins, "allowedOrigins 切出来是空的——正则失效了，不是白名单空了"
    return origins


def _matches_origin(pattern: str, origin: str) -> bool:
    """manifest 的 match 模式能不能覆盖这个来源。

    只处理 `<scheme>://<host>/*` 这一种（这个仓用的全是它）。
    通配主机（`*.example.com`）也认，因为它确实会命中。
    """
    parsed = urlparse(pattern.replace("*://", "https://", 1))
    if not parsed.netloc:
        return False
    target = urlparse(origin)
    host = parsed.netloc
    if host.startswith("*."):
        return target.netloc == host[2:] or target.netloc.endswith(host[1:])
    return f"{parsed.scheme}://{host}" == origin or host == target.netloc


def test_扩展送人去的那个来源_必须能注入桥() -> None:
    origin = _library_origin()
    matches = _manifest_bridge_matches()
    assert any(_matches_origin(pattern, origin) for pattern in matches), (
        f"runtime-config 让扩展把人送去 {origin}，\n"
        f"而 manifest 只在这些来源上注入 bridge.js：{matches}\n"
        "  → 页面打开了也配不上，/v1/* 永远 401「扩展尚未授权或令牌已失效」，\n"
        "    界面永远转圈。这正是 2026-08-17 之前那三个星期的形状。")


def test_扩展送人去的那个来源_必须过得了桥自己的白名单() -> None:
    """**第二张名单。** bridge.js 第一行就是

        if (!allowedOrigins.has(location.origin)) return;

    内容脚本注进来了，来源不在集合里照样当场退出——只改 manifest 等于没改。
    """
    origin = _library_origin()
    allowed = _bridge_allowed_origins()
    assert origin in allowed, (
        f"runtime-config 让扩展把人送去 {origin}，\n"
        f"而 bridge.js 的白名单是：{sorted(allowed)}\n"
        "  → 脚本注进去了，第一行就 return，桥搭不起来。")


def test_两张名单必须彼此对得上() -> None:
    """**反方向**：白名单里有、而 manifest 不注入的来源，是死条目。

    死条目本身不致命，但它会让人以为「那个来源是支持的」——
    这次就是靠读这两张名单才定位到问题的，名单说谎会把下一个人带偏。
    """
    matches = _manifest_bridge_matches()
    allowed = _bridge_allowed_origins()
    orphans = [one for one in sorted(allowed)
               if not any(_matches_origin(pattern, one) for pattern in matches)]
    assert not orphans, (
        f"bridge.js 白名单里这些来源，manifest 根本不会把脚本注进去：{orphans}\n"
        "  两张名单必须一起改。")


def test_那个地址必须真的进得去() -> None:
    """**这才是会从第一天就红的那一条。**

    先写的三条守的是「三处名单彼此一致」——而出事那天它们**本来就一致**
    （都指向 `social-archive.linzezhang.com`），我的前三条在缺陷上会全绿。
    是跑反例时才发现的：把 library_url 改回旧域名，四条一条没红。

    真正的不变量不是「彼此一致」，是**那个地址真的打得开**。
    一致地指向一堵进不去的墙，一致得毫无意义。

    判据：GET library_url，必须 200，且不许被重定向到别的主机
    （登录墙的形状就是 302 到另一个域）。网络不通时跳过——
    跳过会打印原因，不会静悄悄变成绿的。
    """
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    import pytest  # noqa: PLC0415

    origin = _library_origin()
    request = urllib.request.Request(origin + "/", headers={"User-Agent": "Mozilla/5.0 (pair-check)"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:  # noqa: S310
            code = response.status
            landed = urlparse(response.geturl()).netloc
            body = response.read(4096).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        pytest.skip(f"连不上 {origin}（{type(error).__name__}: {error}）——这一条要网络")

    assert code == 200, f"{origin} 返回 {code}，扩展把人送过去只会看到一个错误页"
    assert landed == urlparse(origin).netloc, (
        f"{origin} 被重定向到了 {landed}——扩展送人过去会落在别的域上。\n"
        "  登录墙就是这个形状：页面永远加载不到，bridge 永远注入不上，\n"
        "  于是 /v1/* 永远 401，界面永远转圈。")
    assert "Social Archive" in body, (
        f"{origin} 返回 200 但正文不像资料库（前 200 字：{body[:200]!r}）——"
        "落在登录页或错误页上时也可能是 200。")


def test_这道判据自己不是空扫() -> None:
    """名单被清空、或正则失效时，上面三条会因为「什么都没扫到」而恒真。

    所以把扫到的东西本身也断言一遍。
    """
    assert len(_manifest_bridge_matches()) >= 2, "manifest 注入名单少得不像话"
    assert len(_bridge_allowed_origins()) >= 2, "bridge 白名单少得不像话"
    assert _library_origin().startswith("https://"), "library_url 不是 https"
