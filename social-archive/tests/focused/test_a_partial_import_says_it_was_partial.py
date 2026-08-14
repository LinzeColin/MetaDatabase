r"""导进了东西**但没跑完**时，那句话必须两件都说（2026-08-12）。

## 生产实测：他那 4 次全在这个格子里

    bilibili   导入 102 / 发现 102   partial   RELATION_SCOPE_UNCONFIRMED
    douyin     导入  35 / 发现  35   partial   STABLE_END_WITHOUT_PROOF
    bilibili   导入  67 / 发现  67   partial   RELATION_SCOPE_UNCONFIRMED
    douyin     导入  56 / 发现  56   partial   STABLE_END_WITHOUT_PROOF

他 20 次同步里**真的导进东西的只有这 4 次**，而 `describe_sync_outcome` 里
`if imported > 0` 排在最前面直接 return，于是 4 次说的都是一句
**「新增 N 条。」**——没跑完这件事一个字都没提。

下面那条 `INCOMPLETE_RUN_CODES` 分支（「这次同步卡住了，没有正常结束」）
**在 imported > 0 时永远到不了**，而他的情况恰恰全部是 imported > 0。
一条永远走不到的分支，和没有它是一回事。

## 为什么这不是措辞问题

`discovered == imported`：它把**找到的**都拿回来了，却证不出「确实到头了」——
也就是可能还有没被发现的。他看到「新增 102 条」会合理地以为同步完成了；
而从 2026-08-04 起再没进过一条。验收条件第 1 条要的正是这个诚实度。

## 三条一起钉

数要在、没跑完要说、**其余各类不许被波及**。
只钉前两条，会诱使人把那半句无差别加到所有成功上；
只钉第三条，等于把这个缺陷本身钉住。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.failure_copy import (  # noqa: E402
    INCOMPLETE_RUN_CODES,
    SCROLL_PARTIAL_CODES,
    describe_sync_outcome,
)

# 取自 2026-08-12 的生产实测，不是我编的。
HIS_REAL_RUNS = [(102, "RELATION_SCOPE_UNCONFIRMED"), (35, "STABLE_END_WITHOUT_PROOF"),
                 (67, "RELATION_SCOPE_UNCONFIRMED"), (56, "STABLE_END_WITHOUT_PROOF")]


def _say(imported: int, code: str | None) -> str:
    return str(describe_sync_outcome(imported=imported, failure_code=code,
                                     platform_label="B站", status="partial",
                                     updated_at=None)["message_zh"])


@pytest.mark.parametrize("imported,code", HIS_REAL_RUNS)
def test_his_real_runs_say_both_things(imported: int, code: str) -> None:
    said = _say(imported, code)
    assert str(imported) in said, f"数没了：{said}"
    assert "没跑完" in said, f"**没跑完这件事被吞掉了**：{said}"


@pytest.mark.parametrize("code", sorted(INCOMPLETE_RUN_CODES - SCROLL_PARTIAL_CODES))
def test_every_incomplete_code_discloses_it(code: str) -> None:
    """不是只修他撞到的那两个码——这一类**每一个**都要说。

    只修撞到过的，等于等着下一个码再瞒他一次。

    **减掉 SCROLL_PARTIAL_CODES**：我第一版写的是「每一个」，
    而 `PARTIAL_BY_PAGE_SCROLL` 两个集合里都有。对它「没跑完」虽然是真的，
    「再同步一次试试」却是假出路——不往下滚，再点一次读到的还是同一批。
    是仓里已有的那条判据拦下我的，拦得对。那一类有自己那句
    「往下滚一会儿再同步」，比我这句有用。
    """
    assert "没跑完" in _say(50, code)


def test_the_scroll_partial_code_keeps_its_own_better_advice() -> None:
    """把上面那条减法本身也钉住。

    否则哪天有人「顺手」把 scroll 那一类也纳进来，
    换来的是一颗点了没用的按钮，而判据不会吭声。
    """
    for code in sorted(SCROLL_PARTIAL_CODES):
        assert "再同步一次试试" not in _say(0, code)
        assert "往下滚" in _say(0, code)


def test_a_clean_success_is_not_polluted() -> None:
    """**这条是防止我修过头的。**

    把那半句无差别加到所有成功上，就变成了另一种谎：一次真的跑完的同步
    被说成「可能还有没取到的」，他会去重复点同步找不存在的东西。
    """
    said = _say(56, None)
    assert said == "新增 56 条。", f"干净的成功被污染了：{said}"


def test_a_recoverable_failure_with_items_keeps_the_old_wording() -> None:
    """「中途出过可恢复的错」和「没到底」不是一回事。

    原来那句注释写的就是「即使中途有过可恢复的失败也先报数」——那是对的，
    这次只给 INCOMPLETE 那一类补话，别把这条规则一起改掉。
    """
    said = _say(56, "BROWSER_SCAN_FAILED")
    assert said == "新增 56 条。", f"可恢复失败那一档被波及了：{said}"


def test_zero_import_still_uses_the_stalled_sentence() -> None:
    """imported=0 时走的还是原来那条，别把它也改了。"""
    said = _say(0, "RELATION_SCOPE_UNCONFIRMED")
    assert "卡住" in said and "都还在" in said


def _all_known_codes() -> list[str]:
    # 四个集合全在函数里 import：这条判据不该依赖模块级导入了哪几个名字，
    # 否则换个文件抄过去就 NameError（我试打时正好撞到）。
    from social_archive.failure_copy import (COPY_BY_CODE, INCOMPLETE_RUN_CODES,
                                             SCROLL_PARTIAL_CODES, _ALIASES)
    return sorted(set(COPY_BY_CODE) | set(_ALIASES)
                  | set(INCOMPLETE_RUN_CODES) | set(SCROLL_PARTIAL_CODES))


@pytest.mark.parametrize("code", _all_known_codes())
def test_no_code_breaks_when_something_was_actually_imported(code: str) -> None:
    """**每个码都要用 `imported>0` 扫一遍。**

    `test_failure_copy_matrix.py` 有一条把所有码用 `imported=0` 扫一遍的判据，
    而 `describe_sync_outcome` 第一条分支就是 `if imported > 0`——
    也就是说**「有新增」那一整档从来没有被任何一条判据扫过**。
    2026-08-12 的缺陷正落在那里，而且是靠人读生产数据发现的，不是门。

    这条是那条 `imported=0` 扫描的对称面：不判措辞，只判三件硬的——
    说得出话、数还在、不泄漏内部码。措辞由上面那几条按类判。
    """
    said = _say(7, code)
    assert said.strip(), f"{code} 在有新增时说不出话——他会看到一片空白"
    assert "7" in said, f"{code} 把「新增 7 条」弄丢了：{said}"
    assert not (any(ch.isupper() for ch in said) and "_" in said), (
        f"{code} 的句子里疑似有内部码：{said}")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
