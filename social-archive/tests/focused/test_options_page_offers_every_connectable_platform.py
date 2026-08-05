"""说得出「去连接它」的平台，设置页就必须真给出那张卡片（v0.0.0.7 / T06）。

## 抓到它的那一刻

2026-08-05，我在服务端写下 youtube 的下一步：「点插件里的「连接」」。
写完顺手去核那个按钮到底叫什么——**结果发现按钮不存在**：

    options.js:5  platformOrder = ["generic-web","xiaohongshu","douyin",
                                   "kuaishou","bilibili","x","reddit","instagram"]

**没有 youtube。** 设置页按这张表出卡片，没有卡片就没有「连接账号」按钮。
也就是说交接里让 Owner 做的第二件事（连接 YouTube）**当时根本做不了**，
而我刚给它写了一句更具体的假下一步。

## 为什么之前那些判据都没抓到

同一天已经为 youtube 做过：四张表的真浏览器接线演练（检测 / 权限 / 中文名 /
关系地址）、Cookie 托管两个方向、服务端 CUSTODIAL_PLATFORMS。**全绿。**

因为它们问的都不是「设置页会不会给出这张卡」。options.js 里那三张表
（platformOrder / platformNames / platformIcons）是第五、六、七张，
**从来没有任何东西看过它们**。

「接上了」这件事，每次都是在我以为已经查全之后，又冒出一张表。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.registry import CONNECT_IS_CLICKABLE_TODAY  # noqa: E402

OPTIONS = (ROOT / "apps/browser-extension/options.js").read_text(encoding="utf-8")


def _array(name: str) -> list[str]:
    found = re.search(rf"const {name}\s*=\s*\[([^\]]*)\]", OPTIONS)
    assert found, f"options.js 里找不到 {name}"
    return re.findall(r'"([^"]+)"', found.group(1))


def _object_keys(name: str) -> set[str]:
    found = re.search(rf"const {name}\s*=\s*\{{(.*?)\}};", OPTIONS, re.S)
    assert found, f"options.js 里找不到 {name}"
    return set(re.findall(r'(?:"([^"]+)"|([A-Za-z_][\w-]*))\s*:', found.group(1))) and {
        (a or b) for a, b in re.findall(r'(?:"([^"]+)"|([A-Za-z_][\w-]*))\s*:', found.group(1))
    }


def test_every_platform_we_call_connectable_has_a_card() -> None:
    """**没有卡片就没有按钮，没有按钮那句下一步就是假的。**"""
    order = _array("platformOrder")
    for platform in CONNECT_IS_CLICKABLE_TODAY:
        assert platform in order, (
            f"服务端说 {platform} 点得到，而设置页的 platformOrder 里没有它——"
            "**那张卡根本不会出现，「连接账号」按钮也就不存在**"
        )


def test_every_card_has_a_name_and_an_icon() -> None:
    """卡片出来了但名字是 undefined，等于没接上。"""
    order = _array("platformOrder")
    names = _object_keys("platformNames")
    icons = _object_keys("platformIcons")
    missing_names = [p for p in order if p not in names]
    missing_icons = [p for p in order if p not in icons]
    assert not missing_names, f"这些平台会显示 undefined 当标题：{missing_names}"
    assert not missing_icons, f"这些平台没有图标：{missing_icons}"


def test_the_next_action_names_the_button_that_really_exists() -> None:
    """**那句话里的每个词都要能在界面上找到。**

    第一版写「点插件里的「连接」」，两处都错：按钮叫「连接账号」，
    而且它在设置页、不在 YouTube 页面上。
    """
    for platform, sentence in CONNECT_IS_CLICKABLE_TODAY.items():
        assert "连接账号" in sentence, (
            f"{platform} 那句没有点名真实按钮「连接账号」：{sentence!r}"
        )
        assert "连接账号" in OPTIONS, "设置页里已经没有「连接账号」这个按钮了"
        assert "设置" in sentence, f"{platform} 那句没说要先进设置页"


def test_a_platform_without_a_card_can_never_be_called_clickable() -> None:
    """反过来也钉住：设置页没有的平台，服务端不许说它点得到。

    这是这条判据真正的价值——它必须在**任一侧**改动时都会红。
    """
    order = set(_array("platformOrder"))
    said_clickable = set(CONNECT_IS_CLICKABLE_TODAY)
    assert said_clickable <= order, (
        f"这些平台被说成点得到，而设置页没有它们的卡片：{sorted(said_clickable - order)}"
    )
