r"""查库的那道门和入库那道校验，判「抓重了」用的必须是同一把尺子（2026-08-12）。

## 为什么要钉住

两边本来各写了一套。入口那套认出他库里有 1 条抓重的，查库那道门在**同一份文本**
上报 0——它要求「去掉数字前缀后正好对半分成一样的两半」，而那条标题前一遍
结尾多一个空格，长度成了奇数，两半永远对不上。另外两处窄：`[万千]` 不含「亿」，
以及非要有数字前缀才看。

于是那道门一路是绿的，而它本该拦的东西就摆在他库里。

这个测试用**那条真的骗过它的标题**当夹具（生产原文，不是我编的），
从命令行整个跑一遍那道门——不是去读它的代码。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_his_obsidian_vault_is_intact.py"

# 生产原文。**前一遍结尾那个空格是关键**——正是它让老判据算不出对半分。
FOOLED_THE_OLD_RULE = ("2.2万厂二代卖掉父亲的公司，未必是一代不如一代 "
                       "厂二代卖掉父亲的公司，未必是一代不如一代")
CLEAN = "厂二代卖掉父亲的公司，未必是一代不如一代"


def _run(vault: Path) -> dict:
    done = subprocess.run([sys.executable, str(CHECKER), "--vault", str(vault)],
                          capture_output=True, text=True, timeout=120)
    return json.loads(done.stdout)


def _note(folder: Path, name: str, title: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}-abcdef12.md").write_text(
        f"---\nauthor: null\n---\n\n# {title}\n\nhttps://www.douyin.com/video/7\n",
        encoding="utf-8")


def test_the_gate_sees_the_title_that_fooled_its_old_rule(tmp_path: Path) -> None:
    _note(tmp_path / "Social Archive" / "douyin", "bad", FOOLED_THE_OLD_RULE)
    assert _run(tmp_path)["measured"]["title_is_a_doubled_caption"] == 1


def test_the_gate_leaves_a_real_title_alone(tmp_path: Path) -> None:
    """反面：正当标题不许被算成抓重，否则这道门只是恒红。

    这两条都是生产原文里的好标题，一条以计数开头，一条首尾撞了同一个标签。
    """
    folder = tmp_path / "Social Archive" / "douyin"
    _note(folder, "clean", CLEAN)
    _note(folder, "counts", "14万亿巨额放水+50万亿存款到期，微观体感寒冷，钱到底去哪了？")
    _note(folder, "hashtag", "老布探险原创的烈马等高线皮肤，私人订制将是老布探险的优势之一😁"
                             " #烈马bronco #越野改装 #汽车贴膜 #老布探险")
    assert _run(tmp_path)["measured"]["title_is_a_doubled_caption"] == 0


def test_both_sides_agree_title_by_title() -> None:
    """两边同一把尺子——不是「都能跑」，是**逐条给同一个答案**。

    直接比 `undouble_title` 和入库校验在同一批文本上的结论；哪天有人给其中
    一边加了特例，这里就红。
    """
    from social_archive.models import CaptureRequest
    from social_archive.title_repair import undouble_title

    for title in (FOOLED_THE_OLD_RULE, CLEAN, "14万亿巨额放水+50万亿存款到期，微观体感寒冷，钱到底去哪了？",
                  "26.1万谁敢点开这个bgm谁敢点开这个bgm", "6.6万"):
        at_the_door = CaptureRequest(platform="douyin",
                                     url="https://www.douyin.com/video/7", title=title).title
        assert at_the_door == undouble_title(title), title
