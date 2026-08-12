r"""新加一颗平台级按钮，不许从「假承诺」那道判据底下溜过去（2026-08-12）。

## 为什么补这一道

`find_affordances_the_backend_says_cannot_work.py` 是守 Owner 那条硬要求的
——「绝不给一颗结构上不可能成功的按钮」。它原来只在**两个写死的标记**
（`data-sync-account`、`data-connect-platform`）里找。

我拿一颗 `data-sync-platform` 去撞它，它一声不吭地放行了。
那次反例其实**不成立**（本仓根本没有这个标记，所以那不是真回归），
但它暴露的事是真的：**那张清单靠人维护，而新加一颗按钮不会提醒任何人。**
「判据扫的集合比实况小」这个形状在本仓已经咬过八次。

现在判据会把「不认识的平台级标记」当场打红，逼人去决定它算不算承诺。
这个测试钉住三件事：分类表覆盖了界面上真实存在的每一颗；不认识的会被认出来；
以及**判据现在真的是绿的**（不是因为它谁也认不出来）。
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "find_affordances_the_backend_says_cannot_work.py"


def _load():
    spec = importlib.util.spec_from_file_location("affordance_auditor_under_test", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_every_platform_level_marker_in_the_real_ui_is_classified() -> None:
    """界面上每一颗平台/账号级按钮，判据都得表过态：算承诺，还是算下游。

    这是覆盖率断言，不是行为断言——**它红的时候意思是「有人加了按钮没人决定它算什么」**。
    """
    module = _load()
    known = set(module.PROMISING_MARKERS) | set(module.KNOWN_DOWNSTREAM_MARKERS)
    for relative in ("apps/browser-extension/options.js", "apps/pwa/app.js"):
        text = (ROOT / relative).read_text(encoding="utf-8", errors="ignore")
        found = set(module.PLATFORM_LEVEL_MARKER.findall(text))
        assert found, f"{relative} 里一颗平台级标记都没扫到——正则多半失效了"
        unclassified = sorted(found - known)
        assert not unclassified, (
            f"{relative} 有判据没表过态的平台级按钮：{unclassified}。"
            "先决定它算不算「承诺这个平台能用」再合并。")


def test_the_marker_pattern_actually_matches_the_shape_it_claims_to() -> None:
    """防空转：正则要真的能从一段 HTML 里抠出标记来，也不能宽到什么都抓。"""
    module = _load()
    html = '<button data-sync-platform="x">同步</button><div data-row-id="7"></div>'
    assert module.PLATFORM_LEVEL_MARKER.findall(html) == ["data-sync-platform"]
    # `data-row-id` 不是平台级动作，不许被抓进来，否则这道门会恒红。
    assert "data-row-id" not in module.PLATFORM_LEVEL_MARKER.findall(html)


def test_an_unknown_marker_is_not_quietly_in_the_allow_lists() -> None:
    module = _load()
    known = set(module.PROMISING_MARKERS) | set(module.KNOWN_DOWNSTREAM_MARKERS)
    assert "data-sync-platform" not in known, (
        "这颗标记是当初溜过去的那个反例；把它加进白名单等于把这道门关掉")


def test_the_auditor_passes_on_the_repo_right_now() -> None:
    """**它现在必须是绿的。** 上面三条都可能在一个恒红的判据上通过。"""
    done = subprocess.run([sys.executable, str(CHECKER)],
                          capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr
    assert re.search(r"检查了 [1-9]\d* 处", done.stdout), (
        f"它说自己一处都没检查——那不叫通过：\n{done.stdout}")
