r"""徽章能对他说的每一句话，说明书里都要查得到（2026-08-13）。

## 已有的那道判据只管一个方向

`test_the_guide_quotes_sentences_the_product_still_says.py` 管的是
**说明书 → 产品**：说明书里引的句子，产品必须还在说（防止文档写愿景）。

**反过来那一侧一直没人管**：产品能说、而说明书从来没提过的句子。
他在屏幕上看到一句没见过的话，翻说明书查无此条——那就等于没有说明书。

2026-08-13 实测，备份那条链的四句话里说明书只覆盖了一句：

    「…停下来的是『再存一份到别处』这件事。」          ✅ 有
    「已经 N 小时没有做出新的备份了…」                  ✗ 无
    「最近一次备份没跑完…这一轮的副本没有做上去。」    ✗ 无
    「还没有做出过任何一次备份。」                      ✗ 无

后三句都是**当天新加的信号**——加信号的时候没同时加说明。
和同一天那个「`/health` 多了一格而界面没读」是同一类：
**建好了没接上，只是这次没接上的是读的人那一侧。**

## 口径

只管**活性那两条链**会说的话（`_backup_liveness` / `_replication_liveness`
经由徽章能显示的那几句），不管全部 `failure_copy`——
那本词典里多数句子是按错误码给的，另有判据管。写出来免得被当成覆盖了全部。

比的是句子里**不含变量的那一截**（小时数会变），不是整句。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/使用说明.md"

import sys
sys.path.insert(0, str(ROOT / "src"))
from social_archive import failure_copy  # noqa: E402


def _invariant_parts() -> dict[str, str]:
    """每句话里**不随小时数变化**的那一截。

    **键是 `failure_copy` 里那个符号的名字**，不是我随手起的中文标签——
    下面 `test_这张清单必须自己去产品里数` 靠它和产品源码对齐。
    2026-08-14 之前这里是中文标签，于是这张清单**只能靠我记得去加**，
    而我当天就忘了：新增两句 replication 文案，这道门一声不吭地全绿。
    """
    return {
        # replication 停了（这一句说明书早就有）
        "backup_stale_sentence": failure_copy.BACKUP_STALE_TAIL,
        # replication 跑了但没跑完
        "BACKUP_RUN_INCOMPLETE_SENTENCE": failure_copy.BACKUP_RUN_INCOMPLETE_SENTENCE,
        # backup 本身没做出来（2026-08-13 新增）
        "backup_missing_sentence": failure_copy.backup_missing_sentence(53).split("了", 1)[-1],
        # 一次都没备份过
        "NO_BACKUP_YET_SENTENCE": failure_copy.NO_BACKUP_YET_SENTENCE,
        # replication 一次都没跑过（2026-08-14 新增）
        "NO_REPLICATION_YET_SENTENCE": failure_copy.NO_REPLICATION_YET_SENTENCE,
        # replication 的状态文件坏了（2026-08-14 新增）
        "REPLICATION_STATUS_UNREADABLE_SENTENCE":
            failure_copy.REPLICATION_STATUS_UNREADABLE_SENTENCE,
    }


def _symbols_the_badge_can_actually_show() -> set[str]:
    """**去产品源码里数**：那两个活性函数实际引用了 `failure_copy` 的哪几个符号。

    徽章的触发条件就是 `message_zh` 非空，而 `message_zh` 的值全部来自
    这两个函数里的 `failure_copy.X`。所以这个集合就是"徽章能说的话"的真源。

    **用 `ast` 读源码，不 import。** 第一版写的是 `inspect.getsource`，
    那要先 import `social_archive.api`；而这个测试没有设环境变量，
    于是 `settings` 落到生产默认的 `/var/lib/social-archive`，
    直接 `PermissionError` 炸在导入那一步——要测的东西一个字都没测到。
    （预测这条会绿、实际红了，差额就是这个。）

    附带的好处：`ast` 里根本没有注释，所以「我写来解释修复的那句注释
    把判据废掉」那种事在这里结构上不可能发生。
    """
    import ast  # noqa: PLC0415

    tree = ast.parse((ROOT / "src/social_archive/api.py").read_text(encoding="utf-8"))
    wanted = {"_backup_liveness", "_replication_liveness"}
    found: set[str] = set()
    seen_functions: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in wanted:
            continue
        seen_functions.add(node.name)
        for child in ast.walk(node):
            if (isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                    and child.value.id == "failure_copy"):
                found.add(child.attr)

    # **函数改名了要当场知道**，不能悄悄变成"扫了个空集合然后全绿"。
    assert seen_functions == wanted, (
        f"api.py 里找不到这几个活性函数：{sorted(wanted - seen_functions)}。"
        "改名了就把这里一起改——否则这道门会对着空集合永远绿。")
    return found


def _squeeze(text: str) -> str:
    """**比之前先去掉排版**：行首的引用符和全部空白。

    两轮都栽在同一件事上——比的不是句子，是句子加排版：

    1. 第一版直接 `part in guide`。说明书里长句折行，那个换行让它误红。
    2. 改成去空白之后**还是误红**，红的是说明书里**确实有**的那一句：
       它排成引用块，第二行开头那个 `>` 去掉空白后就掉进句子中间了。

    两次都是判据的比法不对，不是产品缺陷。（先看红的是不是真红。）
    """
    lines = [line.lstrip().lstrip(">").lstrip() for line in text.splitlines()]
    return "".join("".join(lines).split())


def test_切出来的那几截自己得是像样的() -> None:
    """**`split("了", 1)[-1]` 这种切法会悄悄挪。**

    句子一改，切点就跑到别处，切出来的短串**碰巧也在文档里**——
    于是这条判据什么都没在守，却一直是绿的。
    所以先核一遍切出来的东西本身：够长、且不含数字（小时数会变）。

    2026-08-13 实测四截分别是 43 / 33 / 33 / 12 字。
    """
    for name, part in _invariant_parts().items():
        assert len(part) >= 12, f"{name} 切出来的太短，八成是切点挪了：{part!r}"
        assert not any(ch.isdigit() for ch in part), (
            f"{name} 里还带着数字，小时数一变这条就会误红：{part!r}")


def test_这张清单必须自己去产品里数() -> None:
    """**这道门自己的扫描集，不许靠人记得去维护。**

    2026-08-14 实测的代价：我给 replication 加了两句新文案（"一次都没跑过"、
    "状态记录坏了"），说明书一个字没写，而这道门**全绿**——
    因为它比的是一张手写的四句清单，新句子根本不在它眼里。

    「判据扫的集合比实况小」在这个仓已经数不清第几次。修法不是这次记得补，
    是让清单和产品源码对齐：产品那两个函数引用了哪几个 `failure_copy` 符号，
    这里就必须有哪几个。
    """
    used = _symbols_the_badge_can_actually_show()
    listed = set(_invariant_parts())

    missing = used - listed
    assert not missing, (
        f"产品能说、而这道门没在管的句子：{sorted(missing)}\n"
        "  它们不在清单里，于是「说明书有没有写」从来没被查过。\n"
        "  加进 _invariant_parts()，并把句子写进 docs/使用说明.md。")

    stale = listed - used
    assert not stale, (
        f"清单里有产品已经不说的句子：{sorted(stale)}\n"
        "  留着它会逼说明书保留一段用户永远见不到的话——"
        "  那是**永远变不绿之外的另一种坏**：永远绿着却在守一件不存在的事。")


@pytest.mark.parametrize("name", list(_invariant_parts()))
def test_每一句都能在说明书里查到(name: str) -> None:
    part = _squeeze(_invariant_parts()[name])
    guide = _squeeze(GUIDE.read_text(encoding="utf-8"))
    assert part in guide, (
        f"产品能对他说「{name}」这一句，而说明书里查不到：\n"
        f"  {part!r}\n"
        "他在屏幕上看到一句没见过的话、翻说明书查无此条，就等于没有说明书。\n"
        "加信号的时候要同时加说明——这条判据就是为了不让人只加前一半。")


def test_两句话的区别要写清楚() -> None:
    """**两句长得像，说的是两件事**，说明书必须把区别讲明白，
    否则他会以为是同一件事又说了一遍。"""
    # **和上面同一个比法**：半边压缩半边不压缩，迟早在某个折行上翻车。
    guide = _squeeze(GUIDE.read_text(encoding="utf-8"))
    assert _squeeze("再存一份到别处") in guide and _squeeze("没有做出新的备份") in guide, "两句都要在"
    # 处置不同：一个每 15 分钟跑一次（滞后正常），一个每天一次（出现即真停）
    assert _squeeze("30 小时") in guide or _squeeze("整整漏掉一次") in guide, (
        "没写清「这一句一出现就已经是真停了」——"
        "他会照着上一句的经验等它自己追上，而它不会")
