r"""插件的字节变了，版本号必须跟着变（2026-08-11）。

## 这条是从今天的账里翻出来的

VERSION 停在 `0.0.0.41` 的那段时间**真部署了 11 次**（14:26 → 22:01），
CHANGELOG 靠往版本号后面加 `+` 排了 17 节。这次没出事——
`apps/browser-extension/` 在那段时间一个提交都没有——**但那是运气**。

出事的样子这个仓记过：一天发 6 个不同的扩展包全标 `v0.0.0.22`。
真因就在 `apps/pwa/extension-install.html` 里，这次去读了原文核实：

    const behind = requiredVersion
      && compareVersions(installed || "0", requiredVersion) < 0;

**只比版本号字符串。** 字节变了而字符串没变 → `behind` 为假 →
那一页对他说「✓ 插件已是 vX」并把他送回资料库，当天的修复一个也到不了他手上。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_one_version_means_one_package.py"


def _run() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK), "--brief"],
                          cwd=ROOT, capture_output=True, text=True, check=False)


def test_it_is_green_right_now() -> None:
    """正对照。红了要么是真出了这件事，要么是这道门自己坏了——两种都得看。"""
    done = _run()
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_update_prompt_really_only_compares_version_strings() -> None:
    """**这道门的理由必须站得住。**

    如果那一页哪天改成比内容哈希，这条判据的理由就没了，
    到时候该重新想，而不是让它继续拦着人。
    """
    page = (ROOT / "apps/pwa/extension-install.html").read_text(encoding="utf-8")
    assert "compareVersions(installed" in page, (
        "更新提示不再只比版本号了——这道门的理由变了，去重新想一遍")


def test_it_watches_the_directory_that_actually_ships() -> None:
    """看错目录就等于没看（`my-checkers-are-mis-cut-six-times-in-one-day`）。"""
    source = CHECK.read_text(encoding="utf-8")
    assert 'WATCHED = ("apps/browser-extension",)' in source
    assert (ROOT / "apps/browser-extension/manifest.json").is_file(), (
        "被盯的那个目录不存在了——这道门会恒绿")


def test_the_release_gate_runs_it() -> None:
    """没有调用方的判据不算判据。"""
    gate = (ROOT / "scripts/final_verify.py").read_text(encoding="utf-8")
    assert "check_one_version_means_one_package.py" in gate, (
        "发布门没有调它——那它只在我记得的时候起作用")
