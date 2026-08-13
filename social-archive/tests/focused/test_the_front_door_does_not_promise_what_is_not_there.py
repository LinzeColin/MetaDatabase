r"""仓库门面（README）里引的界面词，必须真的存在（2026-08-14）。

## 它修的是什么

`check_docs_match_the_ui.py` 扫的是 `ROOT/docs/*.md`。
**`README.md` 在仓子目录根上，不在里面**——和 `HANDOFF.md` 同一个盲区。
于是门面上的界面词没有任何东西核过。

2026-08-14 实测查出两类：

**一、一句空头承诺。** 最后一行写着：

> 插件暂时不可用时，首页“粘贴链接，立即保存”仍可使用。

而 `apps/` 下**没有任何**「粘贴链接」或「立即保存」；`apps/pwa/index.html`
里也没有贴 URL 的地方。**那条退路不存在**——而它承诺的正是「插件坏了的时候」，
也就是最需要退路的那一刻。

**二、一份抄旧了的五步流程。** 写着「返回网站并刷新」（现在装好会自动送回）、
点「保存到我的档案馆」（使用说明里那颗叫「保存当前页面」），
而最要紧的一条（解压出来的文件夹要放进「文稿」）一个字没提。
已改成指向 `docs/使用说明.md`——**抄一份会漂的流程，不如指向那份有判据管着的**。

## 口径

- 只查**我们自己的**界面词。Chrome 的「开发者模式」这类第三方界面
  登记在 `THIRD_PARTY_UI` 里，**并且要写清它是谁的**——
  留一个不写理由的白名单，等于给自己一个随手放行的口子。
- 语料和 `check_docs_match_the_ui.py` 一致：`apps/**` 的 .js/.html
  ＋ `failure_copy.py`（服务端下发给人看的那本冻结词典）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

# 中文引号或直角引号里的短中文串
QUOTED = re.compile(r"[“「]([^”」]{2,20})[”」]")

# 不是我们的界面——每一条都要写清它是谁的
THIRD_PARTY_UI = {
    "开发者模式": "Chrome 扩展页自己的开关",
    "加载已解压的扩展程序": "Chrome 扩展页自己的按钮",
    "文稿": "macOS 访达里的 Documents 文件夹",
}

# **只查正文，不查引用块。**
#
# 第一版靠一张「这句是在说旧东西」的关键词清单来跳过说明性的行，
# 结果它没跳过我的**举证句**：「实测 apps/ 下没有任何「粘贴链接」或「立即保存」」——
# 而举证**必须**引用原样，否则读的人不知道在说什么。
# 往清单里再塞两个词只会让它更脆：**说明的措辞是无穷的，清单不是。**
#
# 这个仓里 `>` 引用块按约定是**注解**（历史、为什么这么改），
# 正文才是**指令**（照着点的那几句）。判据要管的是指令。
# 代价写清楚：**有人把一句真指令写进引用块，这道门看不见**——
# 换来的是它不会被每一次诚实的举证打红。
# （今天同一形状已经犯了六次：我写来解释修复的话，打中我自己的判据。）


def _ui_corpus() -> str:
    parts = []
    for path in (ROOT / "apps").rglob("*"):
        if path.suffix in (".js", ".html", ".mjs") and path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    server_copy = ROOT / "src/social_archive/failure_copy.py"
    if server_copy.exists():
        parts.append(server_copy.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_门面里引的界面词都真的在() -> None:
    corpus = _ui_corpus()
    assert corpus, "读不到界面语料——这道判据没法判，不许当成通过"

    problems = []
    checked = 0
    for lineno, line in enumerate(README.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith(">"):
            continue  # 注解，不是指令
        for phrase in QUOTED.findall(line):
            if phrase in THIRD_PARTY_UI:
                continue
            checked += 1
            if phrase not in corpus:
                problems.append(f"README.md:{lineno} 「{phrase}」")

    # **不要求 README 里一定有界面词。**
    #
    # 第一版在这里断言 `checked > 0`，防的是"扫了个空集合还全绿"。
    # 但 2026-08-14 把门面改成**指向使用说明**之后，正文里本来就不该再有
    # 按钮指令了——那条断言等于在要一个不该存在的东西。
    # 换成下面那条**自检**：证明这套检测本身还能判（见 test_这套检测本身还能判）。

    assert not problems, (
        "仓库门面上引了界面里没有的词：\n  " + "\n  ".join(problems) + "\n\n"
        "  门面是第一眼看的东西，照着它点一个不存在的按钮，人只会以为是自己错了。\n"
        "  要么改文案，要么——如果那确实是别人家的界面——"
        "写进 THIRD_PARTY_UI 并说清它是谁的。")


def test_第三方白名单每一条都写了是谁的() -> None:
    """**不写理由的白名单，就是给自己一个随手放行的口子。**"""
    blank = [k for k, why in THIRD_PARTY_UI.items() if not why.strip()]
    assert not blank, f"这几条登记成第三方界面却没写是谁的：{blank}"


def test_这套检测本身还能判() -> None:
    """**先拿两个已知答案自检，再去判 README。**

    不这样做的话，语料读空／正则失效时这道门会安静地全绿，
    而那种绿和「门面很干净」长得一模一样。
    （这个仓栽过：屏蔽器只实现了旧接口，什么都没拦住而门照样绿。）
    """
    corpus = _ui_corpus()
    # 正对照：一个确定在界面里的词
    assert "保存当前页面" in corpus, (
        "连「保存当前页面」都在语料里找不到——语料读错了，这道门此刻判不了任何东西")
    # 负对照：一个确定不在的词
    assert "这串字绝不会出现在界面里12345" not in corpus, "负对照命中了，正则/语料有问题"
    # 正则本身
    assert QUOTED.findall("请点「保存当前页面」试试") == ["保存当前页面"], "取词的正则失效了"
