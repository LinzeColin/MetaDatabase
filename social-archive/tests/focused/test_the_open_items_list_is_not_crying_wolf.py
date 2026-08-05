"""那份「还没做」的清单，别把做完的也算进去（v0.0.0.7 / T18）。

`list_open_items.py` 靠**键名**认待办（`still_open`、`NOT_RUN`…）。
问题是键名是当时起的，**正文才是后来的结论**：
`still_unfixed_nearby` 这种名字一旦写下就没人回去改，而它的正文早已被
更新成「**已修（2026-08-04）**」。

2026-08-05 实测 21 条里有 2 条是这样。清单每多报一条做完的，
它离「狼来了」就近一步——而这份清单存在的全部理由，
是让人**真的去看**里面还剩什么。
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LISTER = ROOT / "scripts/list_open_items.py"
_spec = importlib.util.spec_from_file_location("_open_items", LISTER)
_lister = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lister)
SOURCE = LISTER.read_text(encoding="utf-8")


def _walk(node) -> list[str]:
    out: list[str] = []
    _lister.walk(node, "", out)
    return out


def test_a_still_open_key_is_reported() -> None:
    """**先验它会报。** 一份什么都不报的清单没有意义。"""
    assert _walk({"a": {"still_open": "这件事真的没做"}})


def test_a_claim_quoted_under_an_obsolete_heading_is_not_a_todo() -> None:
    """**父层已经说了「这条不成立了」，子层就不是待办。**

    T06 那份把作废的旧说法收在 `已经不成立的` 底下，而旧说法本身带着
    「尚未」二字——于是它被当成未完成项报出来。那不是待办，
    是一条**被引用的、已经失效的旧话**。
    """
    quoted = {"rechecked": {"已经不成立的": {"「凭据尚未创建」": "**已经建好了**"}}}
    assert not _walk(quoted), "引用一句作废的旧话，被当成了新的待办"


def test_it_flags_resolved_looking_items_without_reclassifying_them() -> None:
    """**脚本不替人下结论。**

    自动改判会误伤——「…仍未实现。但推迟的理由**已经不成立**」这种句子里
    也有「已经不成立」四个字，而它仍是未完成。所以只标出来请人确认。
    """
    assert "RESOLVED_HINTS" in SOURCE
    assert "脚本不替你下结论" in SOURCE
    # 关键：被标出来的仍然**算在总数里**，不是被悄悄扣掉
    assert "所以它们仍被算进上面那个数" in SOURCE


def test_it_is_never_a_gate() -> None:
    """未完成项本来就该存在——让它变红只会逼人删条目。"""
    assert "return 0" in SOURCE
    assert "这不是门" in SOURCE
    for red in ("sys.exit(1)", "return 1"):
        assert red not in SOURCE, f"它变成门了：{red}"
