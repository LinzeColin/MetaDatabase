"""「下一步」说点得到的，插件里就必须真有那个按钮（v0.0.0.7 / T13）。

## 抓到它的那次实测

2026-08-05 在生产上把九个被挡住的连接器逐个打出来看理由，youtube 那一条是：

    说明     本版本还不能自动读取 YouTube 的稍后观看和播放列表。
             **现在可以：连接 YouTube（把登录状态交给你自己的服务器保管）**……
    下一步   **本版本没有能打开这条路的设置项**；照上面那句话做就行。

两句话自相矛盾，而后一句否掉的正是交接里**唯一让 Owner 去做的那件事**。

成因是老问题的第五次：同一天给 youtube 接上了插件那四张表，
**没回头改服务端这一张**。

## 这些判据钉的是什么

「服务端说点得到」与「插件里真有按钮」必须同时成立。
任一侧单独改动都要让它红——那正是这次漏掉的形态。
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.credentials import (  # noqa: E402
    CUSTODIAL_PLATFORMS,
    DOMESTIC_PLATFORMS,
)
from social_archive.registry import CONNECT_IS_CLICKABLE_TODAY  # noqa: E402

COOKIE_EXPORT = (ROOT / "apps/browser-extension/cookie-export.js").read_text(encoding="utf-8")
CATALOG = (ROOT / "apps/browser-extension/content/platform-catalog.js").read_text(encoding="utf-8")
SHARED = (ROOT / "apps/browser-extension/shared.js").read_text(encoding="utf-8")


def _extension_allows_custody(platform: str) -> bool:
    """插件的 Cookie 导出白名单里有没有它。"""
    block = COOKIE_EXPORT.split("ALLOWED_PLATFORMS", 1)[-1].split("FORBIDDEN_PLATFORMS", 1)[0]
    return re.search(rf"['\"]?{re.escape(platform)}['\"]?\s*:", block) is not None


def test_every_clickable_platform_really_has_the_button() -> None:
    """**说点得到，插件里就得真有。** 否则等于把人支去找一个不存在的按钮。"""
    assert CONNECT_IS_CLICKABLE_TODAY, "这张表空了——那 youtube 那句矛盾就又回来了"
    for platform in CONNECT_IS_CLICKABLE_TODAY:
        assert _extension_allows_custody(platform), (
            f"{platform} 被说成点得到，而插件的 Cookie 导出白名单里没有它"
        )
        assert platform in CUSTODIAL_PLATFORMS, (
            f"{platform} 被说成点得到，而服务端 CUSTODIAL_PLATFORMS 里没有它"
        )
        # 目录里的键是**不带引号**的（`youtube: Object.freeze({...})`）。
        # 第一版按 `"youtube"` 找，红了——而 youtube 明明在里面，
        # 真浏览器里的接线演练早就验过它的中文名和关系地址。
        # **判据自己写错了形状，不是产品坏了。**
        assert re.search(rf"^\s*{re.escape(platform)}\s*:", CATALOG, re.M), (
            f"{platform} 不在 platform-catalog 里，界面上会显示内部 id"
        )
        assert platform in SHARED, f"{platform} 不在 shared.js 的平台规则里，页面都认不出来"


def test_a_domestic_platform_can_never_be_listed_as_clickable() -> None:
    """**硬边界：国内平台的 Cookie 永不出浏览器。**

    这张表说的是「把登录状态交给你自己的服务器保管」——
    国内四平台一个都不能进来。
    """
    for platform in CONNECT_IS_CLICKABLE_TODAY:
        assert platform not in DOMESTIC_PLATFORMS, (
            f"**{platform} 是国内平台，它的 Cookie 绝不能离开浏览器**"
        )


def test_the_sentence_tells_you_where_to_click() -> None:
    """一句「去连接吧」没有用——**得说清点哪儿**。

    Owner 说过他没有技术基础。指不到具体位置的下一步，和没有下一步差不多。
    """
    for platform, sentence in CONNECT_IS_CLICKABLE_TODAY.items():
        assert "点" in sentence, f"{platform} 那句没说要点什么"
        assert "插件" in sentence or "扩展" in sentence, f"{platform} 那句没说在哪儿点"
        assert len(sentence) >= 20, f"{platform} 那句太短，说不清位置：{sentence!r}"


def test_platforms_held_by_a_gate_are_not_called_clickable() -> None:
    """**「服务端支持托管」不等于「他现在点得到」。**

    x 压着零费用硬门（Owner 不确认就没有任何设置项能开），
    instagram 的授权那步还没做成他点得到的界面。两个都在 CUSTODIAL_PLATFORMS 里，
    但都**不该**出现在这张表里——直接拿 CUSTODIAL_PLATFORMS 当答案就会错。
    """
    assert "x" not in CONNECT_IS_CLICKABLE_TODAY, "x 压着零费用门，没有设置项能打开它"
    assert "instagram" not in CONNECT_IS_CLICKABLE_TODAY, (
        "instagram 的授权那步还没有 Owner 点得到的界面"
    )
    assert CONNECT_IS_CLICKABLE_TODAY.keys() != CUSTODIAL_PLATFORMS, (
        "这张表被写成了 CUSTODIAL_PLATFORMS 的副本——那两件事不是一回事"
    )


def test_the_blanket_sentence_is_still_there_for_everyone_else() -> None:
    """八个平台确实没有设置项可开，那句话对它们是真的，不许一起删掉。"""
    registry_source = (ROOT / "src/social_archive/registry.py").read_text(encoding="utf-8")
    assert "本版本没有能打开这条路的设置项" in registry_source
    assert "CONNECT_IS_CLICKABLE_TODAY.get(connector_id)" in registry_source, (
        "覆盖那句通用文案的分支没了"
    )
