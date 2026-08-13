r"""服务端认得的平台，界面上不许整个不存在（2026-08-14）。

## 它修的是什么

`apps/pwa/app.js` 的 `platformOrder` 原来是 8 个：

    ["all", "xhs", "dy", "ks", "bili", "x", "reddit", "ins", "web"]

而服务端 `PLATFORM_RELATIONS` 认 **9** 个 —— 多的那个是 `youtube`。
差额造成三件事同时发生：

  · **连接面板上没有 YouTube 那张卡**（卡片就是从 `platformOrder` 来的）
  · **资料库上没有 YouTube 那一格筛选**（筛选也是从它来的）
  · 而扩展**会**把 youtube.com 认成平台 `youtube`（`shared.js`），
    手动存下来的 YouTube 条目于是只能在「全部」里看到

同时 `docs/使用说明.md` 那张平台表里 YouTube 是列着的，还写着「**能连账号**」——
**界面上根本没有那张卡，那句话是空的。**

快手和 X 同样不能自动同步，却都有卡（卡上明说只能手动保存）。
**九个里只有 YouTube 是缺的**，而缺的方式是"整个不存在"，
不是"存在但说清楚做不到"——后者才是这个产品对不能自动的平台的规矩。

## 这道判据钉的方向

**以服务端为准**：它认得的每一个平台，界面都必须有一格。
反过来（界面有而服务端没有）已经有 `find_affordances_the_backend_says_cannot_work.py`
在管，那一侧的后果是"给一颗结构上不可能成功的按钮"；
这一侧的后果是"这个平台在界面上根本不存在"。**两侧都要有人管。**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "apps/pwa/app.js"

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from social_archive.account_sync import PLATFORM_RELATIONS  # noqa: E402


def _ui_platforms() -> dict[str, str]:
    """界面 `platformOrder` 里的每一格 → 它对应的服务端 id。"""
    text = APP_JS.read_text(encoding="utf-8")

    order_match = re.search(r"const platformOrder\s*=\s*\[([^\]]*)\]", text)
    assert order_match, (
        "app.js 里找不到 platformOrder。改名了就把这里一起改——"
        "否则这道判据会对着空集合永远绿。")
    order = [x.strip().strip('"\'') for x in order_match.group(1).split(",") if x.strip()]

    # platformMeta 里每一格写着 `server: "<服务端 id>"`
    meta = dict(re.findall(r'(\w+):\s*\{[^}]*?server:\s*"([^"]*)"', text))
    assert meta, "app.js 里读不到 platformMeta 的 server 映射"

    return {key: meta.get(key, "") for key in order if key != "all"}


def test_服务端认得的平台界面上都要有一格() -> None:
    ui = _ui_platforms()
    covered = {server for server in ui.values() if server}
    missing = sorted(set(PLATFORM_RELATIONS) - covered)

    assert not missing, (
        f"服务端认得这几个平台，而界面上整个没有它们：{missing}\n"
        "  后果不是「少个功能」：连接面板没有那张卡（连不了）、\n"
        "  资料库没有那一格筛选（只能在「全部」里翻），\n"
        "  而扩展可能照样把那个站的页面认成这个平台并存进来。\n"
        "  不能自动同步不是理由——快手和 X 也不能，它们的卡上写明「只能手动保存」，\n"
        "  那才是这个产品对做不到的平台的规矩：**说清楚，而不是让它消失**。")


def test_界面每一格都指得出一个服务端平台() -> None:
    """反方向的一半：`platformOrder` 里不许有映射不到服务端的空格。

    （给一颗结构上不可能成功的按钮那一侧另有判据管，这里只钉"指得出"。）
    """
    ui = _ui_platforms()
    dangling = sorted(k for k, server in ui.items() if not server)
    assert not dangling, f"界面这几格没有对应的服务端平台：{dangling}"

    unknown = sorted(k for k, server in ui.items() if server not in PLATFORM_RELATIONS)
    assert not unknown, (
        f"界面这几格指向服务端不认得的平台：{unknown}\n"
        "  服务端没跟上时那张卡会失败关闭（写明不能自动同步），\n"
        "  但**先在这里报出来**，比让人从界面上去猜要快。")
