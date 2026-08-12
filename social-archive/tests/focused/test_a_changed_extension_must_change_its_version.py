"""插件改了内容却不改版本号，他就永远不会被告知去更新（2026-08-10）。

## 产品自己怎么判断「他装的是旧版」

`apps/pwa/app.js`：

    outdated: version !== PRODUCT_VERSION

**只比版本号字符串**。而 `minimum_extension_version`（生产上是 0.0.0.9）
管的是另一件事，不参与这个判断。

## 今天撞见的

2026-08-10 一天里发了 **6 个不同的扩展包**，修掉三个结构性缺陷：

  · 「连接 Chrome 书签」在 service worker 里必抛（面板把英文原样显示给他）
  · 「同步进度」点了没反应（手势不跨 sendMessage）
  · 重连 B 站会开出第二个账号

**六个包全部标着 `0.0.0.22`**——和他机器上那份一模一样。于是
`outdated` 恒为 false，资料库不会说「请更新插件」，他点「连接账号」
用的还是带着那三个缺陷的旧包。**今天所有的修复都到不了他手上。**

判据不看"改得多不多"，只看一件机械的事：**VERSION 最后一次变动之后，
有没有提交动过 `apps/browser-extension/`**。有就说明发出去的包和
上一个带版本号的包不是同一个东西，而产品分辨不出来。

## 边界

只看 git 历史，不看工作树里未提交的改动——未提交的东西还没发出去。
不在 git 仓里（比如打包出来的临时目录）就跳过，并说明跳过了。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from social_archive.git_env import clean_git_env                # noqa: E402

# **pathspec 相对 cwd**（这里是 social-archive/），不要写成仓根那一段——
# 第一版写成 `social-archive/VERSION`，git 找不到，判据红在自己的路径上。
EXT = "apps/browser-extension"
VERSION_FILE = "VERSION"


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, env=clean_git_env(),
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        pytest.skip(f"git 不可用或不在仓里：{done.stderr.strip()[:120]}")
    return done.stdout.strip()


def test_the_extension_changed_since_the_last_version_bump() -> None:
    """**改了包就必须改版本号**，否则他那份旧包在产品眼里和新包一样。"""
    last_bump = _git("log", "-1", "--format=%H", "--", VERSION_FILE)
    assert last_bump, f"找不到 {VERSION_FILE} 的最后一次变动——这条判据在空扫"

    after = _git("log", "--format=%h %s", f"{last_bump}..HEAD", "--", EXT)
    changed = [line for line in after.splitlines() if line.strip()]
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert not changed, (
        f"VERSION 还是 {version}，而它最后一次变动之后有 {len(changed)} 个提交动过扩展：\n"
        + "\n".join(f"    {line}" for line in changed[:8])
        + "\n**产品判断「他装的是旧版」只比版本号**（app.js 的 "
        "`outdated: version !== PRODUCT_VERSION`）。版本号不动，"
        "他打开资料库不会看到「请更新插件」，点「连接账号」用的还是旧包——"
        f"这些改动到不了他手上。升版：python3 scripts/bump_version.py <新版本> --apply")


def test_the_staleness_check_still_compares_the_version_string() -> None:
    """**钉住这条判据的前提。** 哪天改成比哈希了，上面那条的理由就要重写。"""
    app = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    assert "outdated: version !== PRODUCT_VERSION" in app, (
        "产品不再用「版本号不等」来判断旧版了——"
        "那上面那条判据的理由要重写（也许它已经能比内容了，那就更好）")


def test_every_version_site_agrees() -> None:
    """升版工具改的是十二个承重位；它们必须一致，否则镜像 tag 和包会对不上。"""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    import json

    manifest = json.loads((ROOT / "apps/browser-extension/manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version, (
        f"manifest 是 {manifest['version']}，VERSION 是 {version}——"
        "他装的插件会自报一个和服务端对不上的版本，安装页会让他反复更新")
