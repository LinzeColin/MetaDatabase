"""说明书里那几条「替他的数据说话」的规则，喂它坏句子必须变红（2026-08-10）。

## 为什么要有这一份

`check_the_guide_matches_the_product.py` 的 ⑤⑥ 两条规则原先埋在 `main()` 里，
而 `main()` 直接从磁盘读那一份说明书。于是**没有任何办法喂一句坏话给它们**——
⑥ 从 2026-08-07 建起来到今天，一次都没有被打红过。这个仓的教训是现成的：
判据没有调用方、或者只有一个永远是绿的调用方，就不算做完。

## 这一类规则守的是什么

说明书是 Owner 唯一会读的那份文档，**而他没有别的办法发现自己被骗了**。
最难发现的一类不是"写错了按钮名"（照着点一下就露馅），
而是**说明书替他的数据下结论**——写的当天是真的，某一天悄悄变成假的，
而那一天没有任何人在场。

已经真出现过三次：

  ⑥「实测你库里 193 条有 33 条是这样」  —— 他一同步就成假话
  ⑦「你库里目前没有这个来源的账号」    —— **他照着第 3 步做完就成假话**
  ⑧「你自己的服务器上，加密存三份」    —— 实测每次都只确认到 2 份

⑦ 是里面最坏的一种：**让它变成假话的，正是说明书自己教他做的那件事。**
"""

from __future__ import annotations

import importlib.util
import json
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_the_guide_matches_the_product.py"
GUIDE = ROOT / "docs/使用说明.md"

_spec = importlib.util.spec_from_file_location("_guide_check", SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_guide_check"] = _module
_spec.loader.exec_module(_module)
judge_prose = _module.judge_prose
copies_confirmed_today = _module._copies_confirmed_today

# 说明书正文 + 产品此刻的真实状态。**正例必须是绿的**——
# 反例红了而正例也红，证明不了判据切在对的地方。
TEXT = GUIDE.read_text(encoding="utf-8")
PERIODS = {360}
CONFIRMED = copies_confirmed_today()


def test_the_real_guide_passes_all_four_prose_rules() -> None:
    assert judge_prose(TEXT, PERIODS, CONFIRMED) == [], judge_prose(TEXT, PERIODS, CONFIRMED)


def test_the_measured_copy_count_is_a_real_number_not_a_guess() -> None:
    """⑧ 比的那个数必须真的读得出来，否则整条规则是在空扫。"""
    assert isinstance(CONFIRMED, int), (
        "读不出实测副本份数——那 ⑧ 这条规则在这台机器上什么也没比")


# ---------------------------------------------------------------- ⑤ 闹钟周期

def test_a_wrong_sync_interval_is_caught() -> None:
    bad = TEXT.replace("每 6 小时", "每 3 小时")
    assert bad != TEXT, "说明里已经没有「每 6 小时」了——这条反例失效了，要重写"
    problems = judge_prose(bad, PERIODS, CONFIRMED)
    assert any("小时" in p and "闹钟" in p for p in problems), problems


def test_an_unreadable_alarm_is_not_a_pass() -> None:
    """读不到就是不知道，不知道不能读成「一致」。"""
    problems = judge_prose(TEXT, set(), CONFIRMED)
    assert any("没数到" in p for p in problems), problems


# ---------------------------------------------------- ⑥ 写死他库里的条数

def test_a_frozen_item_count_is_caught() -> None:
    """**这是 ⑥ 第一次被打红。** 塞回它当初就是被这句话逼出来的那一句。"""
    bad = TEXT.replace(
        "你库里现在就有这样的条目",
        "实测你库里 193 条有 33 条是这样")
    assert bad != TEXT, "锚点句被改过了——这条反例失效了，要重写"
    problems = judge_prose(bad, PERIODS, CONFIRMED)
    assert any("写死了他库里的条数" in p for p in problems), problems


# ------------------------------------------------ ⑦ 断言他库里「没有」

def test_a_negative_claim_about_his_library_is_caught() -> None:
    """把 2026-08-10 之前那句原话塞回去——它当时已经跟着 guide.html 上了生产。"""
    bad = TEXT.replace(
        "真数据要用你自己的账号才验得到",
        "你库里目前没有这个来源的账号，所以对你而言它还没跑过真数据")
    assert bad != TEXT, "锚点句被改过了——这条反例失效了，要重写"
    problems = judge_prose(bad, PERIODS, CONFIRMED)
    assert any("断言他库里" in p for p in problems), problems


def test_a_conditional_sentence_about_the_ui_is_not_a_violation() -> None:
    """**别把不相干的也拖下水。**

    「（还没有任何内容时，中间那颗按钮也是它）」说的是界面在某个条件下的行为，
    不是对他数据的断言。误伤这种句子，会逼人把整条规则关掉——
    那比没有这条规则更坏。
    """
    assert "还没有任何内容时" in TEXT, "锚点句被改过了——这条反例失效了，要重写"
    problems = judge_prose(TEXT, PERIODS, CONFIRMED)
    assert not any("断言他库里" in p for p in problems), problems


# ---------------------------------------------- ⑧ 副本份数必须等于实测

def _stated_copies() -> int:
    """说明书此刻写的是几处——**从原文现读，不写死**。

    2026-08-11 这两条反例因为写死了「2 处」而集体失效：那天实测从 2 变成 3
    （github 那一路修好了），锚点句不再存在，`bad != TEXT` 当场断言失败。
    测试要守的是「多说少说都会被抓」，不是某一个具体的数——
    数字写死一次，就得跟着现实改一次，而改的人未必知道为什么。
    """
    found = re.search(r"能确认拿得回来的是\s*(\d+)\s*处", TEXT)
    assert found, "说明书里那句「能确认拿得回来的是 N 处」不见了——反例失去了锚点"
    return int(found.group(1))


def test_overselling_the_backup_count_is_caught() -> None:
    """说得比实测多：他会以为自己更安全。"""
    stated = _stated_copies()
    problems = judge_prose(TEXT, PERIODS, stated - 1)
    assert any("超售" in p for p in problems), problems


def test_underselling_the_backup_count_is_also_caught() -> None:
    """少说也是说错：他会以为保护比实际更弱。"""
    stated = _stated_copies()
    problems = judge_prose(TEXT, PERIODS, stated + 1)
    assert any("少说了" in p for p in problems), problems


def test_dropping_the_sentence_entirely_is_not_a_pass() -> None:
    """**把话删掉不等于说对了话。**

    ⑧ 如果只在「写了数字」时才比，那把整句删掉就绕过去了——
    而备份份数恰恰是他最没办法自己核实的一句。
    """
    bad = "\n".join(line for line in TEXT.splitlines()
                    if "能确认拿得回来的是" not in line)
    assert bad != TEXT
    problems = judge_prose(bad, PERIODS, CONFIRMED)
    assert any("没数到" in p for p in problems), problems


def test_an_unmeasured_copy_count_is_not_a_pass() -> None:
    """证据文件读不出来时，也不许静默通过。"""
    problems = judge_prose(TEXT, PERIODS, None)
    assert any("没数到" in p for p in problems), problems


# ------------------------------------------------------ 说明书与产品同步

def test_the_published_page_carries_the_same_sentences() -> None:
    """**他读的是 guide.html，不是 Markdown。**

    2026-08-07 改完 Markdown 忘了重新生成 HTML，两道判据当场红了；
    这里把那件事钉住：这几条规则守的每一句，网页上必须也是这一句。
    """
    page = (ROOT / "apps/pwa/guide.html").read_text(encoding="utf-8")
    for sentence in (f"能确认拿得回来的是 {_stated_copies()} 处",
                     "但演练里读的是 62 条假书签，不是你的"):
        assert sentence in page, (
            f"网页上没有这一句：{sentence!r}——"
            "跑一次 scripts/build_guide_page.py 把它重新生成出来")
    assert "你库里目前没有这个来源的账号" not in page, (
        "那句会过期的话还留在他真正打开的那个网页上")


def test_the_evidence_prints_both_numbers_not_just_the_verdict() -> None:
    """只印「一致」的报告，在两边一起漂到同一个错数时仍旧说「一致」。"""
    data = json.loads((ROOT / "evidence/G4/USER_GUIDE_VERIFIED.json").read_text(encoding="utf-8"))
    assert data["backup_copies_confirmed_today"] == CONFIRMED
    assert data["backup_copies_stated_in_guide"] == [CONFIRMED]
