"""装好插件之后，页面必须自己认出来并把人送回首页（v0.0.0.7 / INV-ZERO-BARRIER）。

## Owner 说的目标流程

> 「直接进入主页，然后登录，然后跟着它的提示点击安装插件…
>   如果实在不能靠系统运行的，那么就提供明确的指示，越少越好，越简单越好…
>   **然后当插件准备好之后。就自动回退到首页。**」

## 一句必须写下的实话

**浏览器不允许网页替用户安装扩展。** `chrome://extensions` 是浏览器设置页，
网页碰不到；Chrome 137 起连 `--load-extension` 命令行开关也取消了。
所以「后台自动装好」做不到——这是浏览器的硬约束，不是实现偷懒。

能做到的是把人要做的**减到最少**，并且**不让人去判断「好了没有」**：

  · 步骤从六步减到四步（原来的第 5、6 步「返回网站并刷新」「点击连接」
    本来就可以自动完成，却丢给了人）
  · 页面实时检测，装好即自动回首页

原来这一页是**纯静态**的：装好了也不会有任何反应。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "apps/pwa/extension-install.html"


def visible_text() -> str:
    """去掉注释再看。

    **注释里引用一句旧文案，不等于那句文案还在页面上。**
    本轮已经被自己写的说明文字骗过四次——第一版这条判据就报了假红：
    我在脚本注释里写「原来第 5、6 步写着『返回网站并刷新』『点击连接』」，
    于是判据认为那两步还在。
    """
    html = PAGE.read_text(encoding="utf-8")
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    return "\n".join(
        line for line in html.splitlines()
        if not line.lstrip().startswith("//")
    )


def test_the_page_actually_detects_the_extension() -> None:
    html = PAGE.read_text(encoding="utf-8")
    assert "<script" in html, "这一页还是纯静态的——装好了也不会有任何反应"
    assert "SA_PING" in html, "没有用桥去问「插件在不在」"
    assert 'source: "social-archive-web"' in html, "握手来源写错了，桥不会理它"
    assert '"social-archive-extension"' in html, "不认扩展回来的那条消息"


def test_it_returns_to_home_on_its_own() -> None:
    """不让用户自己判断「好了没有」。"""
    html = PAGE.read_text(encoding="utf-8")
    script = html.split("<script", 1)[1]
    assert 'location.href = "/"' in script, "检测到了却不把人送回首页"
    assert "detectText" in script and "已检测到插件" in html, "没有把检测状态显示出来"


def test_the_steps_are_only_the_ones_a_human_must_do() -> None:
    """能自动的不要写成步骤。原来的第 5、6 步是人替机器干活。"""
    html = visible_text()
    steps = re.findall(r"<li><strong>([^<]+)</strong>", html)
    assert len(steps) == 4, f"步骤应当只剩四步（人必须做的那四下），现在是 {len(steps)}：{steps}"
    for gone in ("返回网站并刷新", "点击连接"):
        assert gone not in html, f"「{gone}」这一步已经自动化了，不该还写在步骤里"


def test_it_says_plainly_that_the_browser_forbids_auto_install() -> None:
    """做不到的事要直说，而不是让用户以为是自己没找到那个按钮。"""
    html = PAGE.read_text(encoding="utf-8")
    assert "浏览器不允许网页替你安装扩展" in html


def test_no_stale_version_string() -> None:
    """这一页曾经写着 v0.0.0.6，而产品早就不是那个版本。"""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    html = PAGE.read_text(encoding="utf-8")
    stale = [m for m in re.findall(r"v?0\.0\.0\.\d", html) if m.lstrip("v") != version]
    assert not stale, f"页面上还留着过期版本号：{stale}"
