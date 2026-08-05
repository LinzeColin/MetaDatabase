"""同一个目的地，三处界面不许叫三个名字（v0.0.0.7 / T11）。

## 实测出来的

目的地名字在三处各写了一份：

    apps/pwa/app.js               destinationNames
    apps/browser-extension/shared.js   DESTINATION_NAMES
    apps/browser-extension/options.js  destinationNames

2026-08-06 比了一遍，**8 个里有 5 个三处不一致**。最难看的是
`social_archive`——**用户自己的档案馆**：

    资料库：Social Archive     扩展：我的档案馆     设置页：主档案

产品在别处一律叫它「档案馆」（全仓 54 处，面向用户的「我的档案馆」14 处，
而「主档案」只出现在那张表里）。**对一个说自己没有技术基础的人，
同一样东西三个名字就是三样东西。**

## 判据

三张表对同一个 id 必须给同一个名字。确实要不一样的，写进
`NAMED_DIFFERENTLY_ON_PURPOSE` 并说清为什么——**登记过的照样列出来**，
不让它变成一个登记完就看不见的口子。

（第 24 道门查的是「每张表都提到了每个目的地」，**它不查名字一不一样**。）
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TABLES = {
    "资料库": ("apps/pwa/app.js", r"const destinationNames = \{(.*?)\};"),
    "扩展共用": ("apps/browser-extension/shared.js",
             r"const DESTINATION_NAMES = Object\.freeze\(\{(.*?)\}\);"),
    "设置页": ("apps/browser-extension/options.js", r"const destinationNames = \{([^\n]*)\};"),
}

# **有意不一样的**，每条写清为什么。扩展那一侧给的是带用途的长名——
# 弹窗与设置页里没有旁边那一段说明文字，多两个字能省一次猜。
NAMED_DIFFERENTLY_ON_PURPOSE = {
    "archivebox": "扩展里叫「ArchiveBox 归档队列」——那一屏没有说明文字，点明它是个队列",
    "github": "扩展里叫「GitHub 私有库」——强调是私有仓，不是公开仓",
    "karakeep": "扩展里叫「Karakeep 阅读器」——点明它是个阅读器",
    "linkwarden": "扩展里叫「Linkwarden 阅读器」——同上",
}


def _table(relative: str, pattern: str) -> dict[str, str]:
    text = (ROOT / relative).read_text(encoding="utf-8")
    found = re.search(pattern, text, re.S)
    assert found, f"{relative} 里那张表找不到了——判据的射程失效，先修判据"
    body = "\n".join(l for l in found.group(1).splitlines() if not l.lstrip().startswith("//"))
    return dict(re.findall(r'(\w+)\s*:\s*"([^"]+)"', body))


def test_the_same_destination_has_the_same_name_everywhere() -> None:
    tables = {name: _table(*spec) for name, spec in TABLES.items()}
    for name, table in tables.items():
        assert len(table) >= 8, f"{name} 只解析出 {len(table)} 项——**解析失败和「都一致」长得一样**"

    clashes = []
    for key in sorted(set().union(*[set(t) for t in tables.values()])):
        if key in NAMED_DIFFERENTLY_ON_PURPOSE:
            continue
        names = {where: table.get(key) for where, table in tables.items() if key in table}
        if len(set(names.values())) > 1:
            clashes.append(f"{key}: " + "／".join(f"{w}={n}" for w, n in names.items()))
    assert not clashes, (
        "**同一个目的地在三处叫了不同的名字**：\n  " + "\n  ".join(clashes)
        + "\n确实要不一样的话，写进 NAMED_DIFFERENTLY_ON_PURPOSE 并说清为什么。"
    )


def test_the_archive_itself_is_called_one_thing() -> None:
    """**用户自己的档案馆，尤其不许有三个名字。**

    它不是某个第三方目的地，是这个产品本身。上面那条通则里
    它已经被覆盖，这条单独钉住它——因为它是最容易被人「顺手改个短的」的那个。
    """
    tables = {name: _table(*spec) for name, spec in TABLES.items()}
    names = {table.get("social_archive") for table in tables.values() if "social_archive" in table}
    assert names == {"我的档案馆"}, f"档案馆自己被叫成了：{names}"
