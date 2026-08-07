"""「今天确认了几份」那条判据，喂它坏形状必须变红（2026-08-07）。

说明书对 Owner 说「数据存在哪？你自己的服务器上，**加密存三份**」。
库里那三行 `verified` 是写入当时的记录，不是今天的事实。今天在他生产机上
真问了一遍：r2 在、oci 在、**github 读不到**（那把 token 解析不了
LinzeColin/Private-Database）——而 GitHub 正是 2026-08-04 迁移之后当主备份的那份。

这条判据把「几份今天确认过」变成一个会说话的数。所以它自己必须会红。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_the_three_copies_are_really_there.py"

_spec = importlib.util.spec_from_file_location("_three_copies", SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_three_copies"] = _module
_spec.loader.exec_module(_module)
summarise = _module.summarise

_OK = {"status": "PASS", "found": {"byte_size": 520, "encryption": "age-x25519"}}


def test_all_three_reachable_passes() -> None:
    """**正例必须是绿的。** 一条永远喊红的判据和永远说 PASS 的一样没用。"""
    problems, measured = summarise({s: [dict(_OK)] for s in ("r2", "oci", "github")})
    assert problems == [], problems
    assert measured["copies_confirmed_today"] == 3


def test_todays_real_shape_is_a_failure() -> None:
    """**当天那份真实形状**：两份在，第三份读不到。"""
    problems, measured = summarise({
        "r2": [dict(_OK)], "oci": [dict(_OK)],
        "github": [{"status": "FAIL", "error_code": "GITHUB_RELEASE_READ_FAILED"}],
    })
    assert measured["copies_confirmed_today"] == 2
    assert any("github" in p for p in problems), problems
    assert any("说明书写的是三份" in p for p in problems), problems


def test_a_store_that_was_never_queried_is_not_a_pass() -> None:
    """**一个都没查 ≠ 通过。** 空默认值吞掉「不知道」，这个仓栽过很多次。"""
    problems, measured = summarise({"r2": [dict(_OK)], "oci": [dict(_OK)], "github": []})
    assert any("一个都没查" in p for p in problems), problems
    assert measured["copies_confirmed_today"] == 2


def test_a_partial_loss_inside_one_store_is_reported() -> None:
    """同一家存储里有的在有的不在——**别被「至少有一个在」盖过去**。"""
    problems, _ = summarise({
        "r2": [dict(_OK), {"status": "FAIL", "error_code": "S3_OBJECT_MISSING"}],
        "oci": [dict(_OK), dict(_OK)], "github": [dict(_OK), dict(_OK)],
    })
    assert any("只有 1 个在" in p for p in problems), problems


def test_the_guide_sentence_this_guards_still_exists() -> None:
    """守的是说明书那句话，那句话得还在。"""
    guide = (ROOT / "docs/使用说明.md").read_text(encoding="utf-8")
    assert "加密存三份" in guide, "说明书那句承诺被改了——这条判据也要跟着改"
