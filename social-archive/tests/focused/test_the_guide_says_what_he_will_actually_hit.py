r"""说明书少说的那一类，也要有人管（2026-08-12）。

`check_the_guide_matches_the_product.py` 查的是**正方向**：说明里写的东西真的存在。
它查不到反方向——**真实存在、而说明里没有**。两个方向漏一个，
说明书就可以靠「少说」永远绿。

漏在第一步上：说明让他打开 social-archive.linzezhang.com，而没有会话时
它先 302 到 Cloudflare Access 的登录页，说明书 `Access`/`验证`/`邮箱`/`Cloudflare`
四个词全是 0 处。他自己的浏览器有会话看不见；换台机器，第一步就卡在
一个说明书没写过的页面上——而那份说明开头写着「每一句都逐条核对过」。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_the_guide_warns_about_the_access_gate.py"


def _module():
    spec = importlib.util.spec_from_file_location("guide_gate", CHECK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_it_reads_the_first_url_the_guide_gives_him() -> None:
    """判据得对着**他真会点的那个地址**，不是我另写一个。"""
    guide = (ROOT / "docs/使用说明.md").read_text(encoding="utf-8")
    url = _module().first_url(guide)
    assert url and url.startswith("https://"), f"读不出第一个地址：{url!r}"
    assert "social-archive" in url


def test_it_judges_both_directions() -> None:
    """**两个方向都要判**，否则它自己就成了一个只会绿的摆设。

    · 挡着而说明没提 → 红
    · 不挡了而说明还留着提醒 → 也红（过期的提醒一样会把人带错）
    """
    source = CHECK.read_text(encoding="utf-8")
    assert "gated and not mentioned" in source, "少了「挡着却没写」那一支"
    assert "not gated and mentioned" in source, "少了「不挡了还留着」那一支"


def test_an_unreachable_url_is_not_a_pass() -> None:
    """这台机器打不到那个地址时，**不许静默算过**。"""
    source = CHECK.read_text(encoding="utf-8")
    assert "这不是通过" in source


def test_the_redirect_target_is_not_dumped_whole() -> None:
    """Access 的跳转带一大段 JWT；原样写进证据既是噪声也会撞密钥扫描。"""
    source = CHECK.read_text(encoding="utf-8")
    assert 'split("?", 1)[0]' in source, "跳转地址没截断——那串 meta= 会整个进证据"


def test_the_deploy_actually_runs_it() -> None:
    """没有调用方的判据不算判据。"""
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert CHECK.name in deploy, f"部署没调 {CHECK.name}"
    step = deploy[deploy.index(CHECK.name):]
    nxt = step.find('\nstep "')
    step = step[:nxt] if nxt > 0 else step
    assert "fail " in step, "它红了不中止部署，等于没验"
