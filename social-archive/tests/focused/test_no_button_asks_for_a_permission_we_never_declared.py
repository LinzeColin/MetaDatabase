r"""不许有一颗**结构上不可能成功**的按钮（2026-08-11）。

## 它守的那条硬要求

Owner 的验收里有一句：不能自动的平台要当场说清，**绝不给一颗结构上不可能
成功的按钮**。「结构上不可能」有一种最安静的形态：

    chrome.permissions.request({ origins: ["https://*.某平台.com/*"] })

如果这个域没有写进 manifest 的 `optional_host_permissions`，Chrome 直接抛
`Requested optional permissions are not declared in the manifest`。
按钮画得出来、点得下去、**永远成功不了**——而这件事在源码里看不出来，
要么等到有人在真浏览器里点它。

同一个形状还有第二条轴：`{ permissions: ["bookmarks"] }` 这种非主机权限，
必须在 `optional_permissions` 或 `permissions` 里。

## 为什么不列白名单

判据的默认答案是「你要的每一样，manifest 里都得有」——
新加一个平台而忘了补 manifest，这条要红。
（`categoryid-taxonomy-must-be-proven`：6 个锚点全对上的映射仍被证伪两处；
列举已知的那几个，挡不住新写进来的错。）

## 边界

它只证明「要的东西声明过了」。**不证明用户真会点允许**，也不证明授予之后
那条读取链跑得通——那两件事分别由真 Chrome 的演练和生产回读管。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "apps/browser-extension"
MANIFEST = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))


def _platform_rules() -> list[tuple[str, list[str]]]:
    """从 shared.js 里把 PLATFORM_RULES 那张表取出来。

    取不到就报错，**不是跳过**——一个悄悄什么都没查的判据比没有还坏
    （`empty-default-swallows-unknown`）。
    """
    source = (EXTENSION / "shared.js").read_text(encoding="utf-8")
    marker = "const PLATFORM_RULES = Object.freeze(["
    assert marker in source, "shared.js 里找不到 PLATFORM_RULES——这条判据的假设过期了"
    block = source[source.index(marker): source.index("]);", source.index(marker))]
    rules: list[tuple[str, list[str]]] = []
    for line in block.splitlines():
        hit = re.search(r'id:\s*"([a-z0-9\-]+)".*?patterns:\s*\[([^\]]*)\]', line)
        if hit:
            rules.append((hit.group(1), re.findall(r'"([^"]+)"', hit.group(2))))
    assert len(rules) >= 8, f"只解析出 {len(rules)} 个平台——正则跟不上这张表了"
    return rules


def test_every_connectable_platform_has_its_origins_declared() -> None:
    declared = set(MANIFEST.get("optional_host_permissions", []))
    assert declared, "manifest 一条可选主机权限都没有——那连账号这件事整个不成立"
    problems: list[str] = []
    for platform, patterns in _platform_rules():
        missing = [p for p in patterns if p not in declared]
        if missing:
            problems.append(f"{platform} 要 {missing}，而 manifest 没声明")
    assert not problems, (
        "有平台会去要一个没声明过的域——`chrome.permissions.request` 当场抛，"
        "那颗「连接账号」结构上永远成功不了：\n  " + "\n  ".join(problems))


def test_every_requested_permission_name_is_declared() -> None:
    """非主机权限那一轴：`{permissions: [...]}` 里的每个名字都得声明过。"""
    allowed = set(MANIFEST.get("optional_permissions", [])) | set(MANIFEST.get("permissions", []))
    asked: set[str] = set()
    for path in sorted(EXTENSION.rglob("*.js")):
        for block in re.findall(r"permissions\s*:\s*\[([^\]]*)\]", path.read_text(encoding="utf-8")):
            asked.update(re.findall(r'"([^"]+)"', block))
    assert asked, "全扩展一处 `permissions: [...]` 都没解析到——这条判据在空转"
    undeclared = sorted(asked - allowed)
    assert not undeclared, (
        f"这些权限被申请但 manifest 里没声明：{undeclared}——"
        "点下去只会抛一句英文，而他看不出那和「连接账号」有什么关系")


def test_a_platform_with_no_origins_is_not_offered_an_impossible_button() -> None:
    """**patterns 为空的平台**不许出现在「点了会去要权限」那条路上。

    `generic-web` 是有意为之：它靠 activeTab，不要主机权限，
    `requestPlatformPermission` 对它直接 return true。这条钉住那个约定——
    要是哪天有个平台既没有 patterns、又走了要权限那条路，
    它会拿到一个空 origins 的 request，Chrome 报错的措辞和「没声明」不是一回事。
    """
    source = (EXTENSION / "shared.js").read_text(encoding="utf-8")
    body = source[source.index("async function requestPlatformPermission"):]
    body = body[:body.index("\n  }") + 4]
    assert "if (!origins.length) return true" in body, (
        "requestPlatformPermission 不再对「没有主机权限的平台」提前返回了——"
        "那种平台会带着空 origins 去 request")
    empty = [pid for pid, patterns in _platform_rules() if not patterns]
    assert empty == ["generic-web"], (
        f"没有主机权限的平台变成了 {empty}——多出来的那些要单独想清楚，"
        "别默认它们和 generic-web 一样走 activeTab")
