r"""使用说明里让他去点的每一样东西，都得真的存在（2026-08-10）。

验收第 2 条写的是「说明里写的每一步都必须被判据验过真的存在，不许写愿景」。
这条判据只做一件很笨但很实的事：把说明书里点名的**文件**和**路由**抓出来，
逐个去仓里找。

它抓的是这一类事故：我今天新加了一颗「只补收藏到 Obsidian.command」并写进说明书，
而**说明书和那个文件之间没有任何东西把它们绑在一起**——
文件改个名、或者哪天没生成，说明书就变成一句假话，而他照着做会发现桌面上没有那个东西。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/使用说明.md"
TEXT = GUIDE.read_text(encoding="utf-8")

# 说明书里点名的双击文件：「xxx.command」
COMMAND_FILES = sorted(set(re.findall(r"「([^」]+\.command)」", TEXT)))
# 说明书里点名的产品地址（他会真的在浏览器里打开的那些）
URLS = sorted(set(re.findall(r"https://[a-z.-]+(/[a-zA-Z0-9/._-]*)", TEXT)))
# 说明书里让他去点的按钮文字
BUTTONS = sorted(set(re.findall(r"「(下载全部 Markdown|导入数据包[^」]*)」", TEXT)))


def test_it_actually_found_things_to_check() -> None:
    """反空扫：一个都没抓到的话，下面每条都会白过。"""
    assert COMMAND_FILES, "说明书里一个 .command 都没抓到——判据在空扫"
    assert URLS, "说明书里一个产品地址都没抓到——判据在空扫"
    assert BUTTONS, "说明书里一个按钮文字都没抓到——判据在空扫"


@pytest.mark.parametrize("name", COMMAND_FILES)
def test_every_command_file_the_guide_names_exists(name: str) -> None:
    """他双击的那个文件，仓里必须有对应的一份（桌面那份由刷新脚本落盘）。"""
    in_repo = (ROOT / "scripts" / name).is_file()
    generated_by = (ROOT / "scripts/refresh_desktop_launcher.py").read_text(encoding="utf-8")
    assert in_repo or name in generated_by, (
        f"说明书让他双击「{name}」，而 scripts/ 里既没有这个文件、"
        f"refresh_desktop_launcher.py 也不生成它——他照着做会发现桌面上没有这东西")


@pytest.mark.parametrize("path", URLS)
def test_every_url_the_guide_tells_him_to_open_is_registered(path: str) -> None:
    """他会照着说明书在浏览器里打开这些地址——服务端得真的有这条路由。"""
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    wanted = path.rstrip("/") or "/"
    assert f'"{wanted}"' in api or f"'{wanted}'" in api, (
        f"说明书让他打开 {path}，而 api.py 里没有注册这条路由——"
        "说明书写的是愿景，不是产品")


@pytest.mark.parametrize("label", BUTTONS)
def test_every_button_the_guide_names_is_on_the_page(label: str) -> None:
    """**说明书说「点右上角那个按钮」，页面上就得真有那几个字。**

    这个仓栽过「说明书里那一步在产品里根本不存在」——
    他照着做，找不到，只能回来问我。
    """
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    assert label in html, (
        f"说明书让他点「{label}」，而 index.html 上没有这几个字")
