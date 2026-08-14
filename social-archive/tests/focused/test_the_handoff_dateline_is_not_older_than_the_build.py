r"""交接首屏那句「当前状态（某月某日）」不许比最后一次升版旧（2026-08-14）。

## 它守的是这份文档的支点

`HANDOFF.md` 第一节开头写着：

> **这一节是当前状态（YYYY-MM-DD）。下面每个数字都是当天从生产上量出来的，不是记忆。**

**这句话是整份交接可信度的支点**——它让读的人知道下面那些数字有多新。
日期一旦落后，这句话本身就成了假的，而它偏偏是用来证明别的东西为真的那一句。

2026-08-14 实测：那一行还写着 `2026-08-13`，而当天已经发到 v0.0.0.93、
版本行、磁盘那条、抽样窗口那条全是当天改的。**一份自称"当天量的"文档，
标着昨天的日期。**（另外三处「最后一次部署（2026-08-13）」同病。）

## 锚点为什么选 git

`evidence/**` 里的时间戳最新停在 2026-08-06（那些是历史证据，不是每次部署重生成的），
而 `final-verification.json` **故意不带生成时间**——带了的话每次部署都会把下一次
挡在「工作树干净」那道门外（CHANGELOG 里记过这件事）。

可靠且在仓里的锚只剩一个：**最后一次改 `VERSION` 的那个提交的日期**。
升版必然改它，所以「升了版没更新日期」当场就会红。
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "HANDOFF.md"

# 钩子塞的 GIT_DIR 会压过 cwd，这个仓为此栽过
_LEAKED_BY_GIT_HOOKS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                        "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")


def _stated_date() -> dt.date:
    text = HANDOFF.read_text(encoding="utf-8")
    match = re.search(r"这一节是当前状态（(\d{4})-(\d{2})-(\d{2})）", text)
    assert match, (
        "HANDOFF.md 首屏找不到「这一节是当前状态（…）」那一行。\n"
        "  写法变了就把这里一起改——否则这道判据会对着空值永远绿。")
    return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _version_commit_date() -> dt.date:
    env = {k: v for k, v in os.environ.items() if k not in _LEAKED_BY_GIT_HOOKS}
    done = subprocess.run(
        ["git", "log", "-1", "--format=%cs", "--", "VERSION"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    out = done.stdout.strip()
    assert done.returncode == 0 and out, (
        f"读不到 VERSION 的最后一次提交日期（退出码 {done.returncode}）。\n"
        "  **不许把读不到当成通过**——那正是这道门要防的那种沉默。")
    return dt.date.fromisoformat(out)


def test_日期不许比最后一次升版旧() -> None:
    stated, built = _stated_date(), _version_commit_date()
    assert stated >= built, (
        f"交接首屏写着「当前状态（{stated}）」，而最后一次升版是 {built}。\n"
        "  那一行紧跟着说「下面每个数字都是**当天**从生产上量出来的」——\n"
        "  日期落后，这句话本身就成了假的，而它是用来证明别的数字为真的那一句。\n"
        "  升版时把它一起改（第一节开头，还有「最后一次部署（…）」那几处）。")


def test_这套检测本身还能判() -> None:
    """**先拿已知答案自检。** 正则失效或 git 读不到时，上面那条会安静地全绿。"""
    stated = _stated_date()
    assert dt.date(2026, 1, 1) <= stated <= dt.date(2100, 1, 1), f"取到的日期不像话：{stated}"
    built = _version_commit_date()
    assert dt.date(2026, 1, 1) <= built <= dt.date(2100, 1, 1), f"git 取到的日期不像话：{built}"
    # 正则本身
    probe = "**这一节是当前状态（2020-01-02）。下面每个数字都是当天…**"
    assert re.search(r"这一节是当前状态（(\d{4})-(\d{2})-(\d{2})）", probe), "取日期的正则失效了"
