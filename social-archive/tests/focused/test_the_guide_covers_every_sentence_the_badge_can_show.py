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
    """每句话里**不随小时数变化**的那一截。"""
    return {
        # replication 停了（这一句说明书早就有）
        "复制停了": failure_copy.BACKUP_STALE_TAIL,
        # replication 跑了但没跑完
        "复制没跑完": failure_copy.BACKUP_RUN_INCOMPLETE_SENTENCE,
        # backup 本身没做出来（2026-08-13 新增）
        "没做出新备份": failure_copy.backup_missing_sentence(53).split("了", 1)[-1],
        # 一次都没备份过
        "从没备份过": failure_copy.NO_BACKUP_YET_SENTENCE,
    }


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
