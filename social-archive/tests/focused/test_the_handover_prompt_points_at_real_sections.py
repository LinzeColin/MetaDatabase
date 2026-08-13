r"""可粘提示词里指的那几节，必须真的存在，而且边界不许靠数数（2026-08-14）。

## 它修的是什么

`HANDOFF.md` 首屏那段可整块复制的提示词，是**整个交接唯一会被读的东西**——
Owner 的计划是「把 GitHub 交给 ChatGPT，一句话 prompt，自己不重新配置任何东西」。
那段话里指路的每一句，接手方都会照着做。

2026-08-14 实测，它写的是：

    先读 social-archive/HANDOFF.md，只读**第一到第六节**（后面是历史，别照着做）。

而这份文档的标题序列是：

    一、它现在是什么
    一之二、「聚合真的发生」这件事，证到哪一步了     ← 夹在中间
    二、…  三、…  四、…  五、坏了怎么办
    六、两条绝对不要碰的

**数标题的话，第 6 个是「五、坏了怎么办」**——正好漏掉「六、两条绝对不要碰的」，
也就是那两条一碰就会花钱或把登录态带出他机器的红线。
「一之二」让「第几节」有了两个答案，而两个答案里错的那个删掉的正是最贵的一节。

## 这道判据钉两件事

1. **提示词里用「」引的每一个小节名，必须真的是 HANDOFF.md 里的一个标题。**
2. **边界不许写成序数区间**（「第一到第六节」这种）。这份文档有非常规编号，
   序数不是一个确定的坐标；要用标题原文当边界，那个数不错。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "HANDOFF.md"


def _prompt_block() -> str:
    """首屏那段可整块复制的提示词（第一个 ``` 围栏）。"""
    text = HANDOFF.read_text(encoding="utf-8")
    fences = re.findall(r"```\n(.*?)```", text, flags=re.S)
    assert fences, "HANDOFF.md 首屏没有可粘提示词的代码围栏——那段是交接的载荷，不能没有"
    return fences[0]


def _headings() -> list[str]:
    return [line[3:].strip()
            for line in HANDOFF.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")]


def test_提示词里引的小节名都真的存在() -> None:
    prompt = _prompt_block()
    headings = _headings()
    quoted = re.findall(r"「([^」]+)」", prompt)
    # 只挑看起来像小节名的（带中文序号前缀），别把普通引用也当成小节
    referenced = [q for q in quoted if re.match(r"^[一二三四五六七八九十]+[、之]", q)]
    assert referenced, (
        "提示词里没有用直角引号点名任何一个小节。**这不是干净**——"
        "它必须给接手方一个确定的阅读边界，否则他会一路读进历史记录。")
    missing = [q for q in referenced if not any(h.startswith(q) or q.startswith(h)
                                                for h in headings)]
    assert not missing, (
        f"提示词点名的小节在 HANDOFF.md 里找不到：{missing}\n"
        f"  现有标题：{headings[:10]}\n"
        "  接手方会照着找，找不到就只能自己猜边界。")


def test_边界不许写成序数区间() -> None:
    """**「第 X 到第 Y 节」这种写法在这份文档上是有歧义的。**

    因为存在「一之二」这样的非常规编号：按标题顺序数和按中文序号数，
    答案不一样。而两个答案里错的那个，删掉的正是「六、两条绝对不要碰的」。
    """
    prompt = _prompt_block()
    ordinal = re.search(r"第[一二三四五六七八九十\d]+到第[一二三四五六七八九十\d]+节", prompt)
    assert not ordinal, (
        f"提示词用序数区间划边界：{ordinal.group(0)!r}\n"
        "  这份文档有「一之二」这种编号，序数不是确定的坐标——"
        "按标题顺序数会少读一节。\n"
        "  改成用标题原文当边界，例如「一直读到「六、两条绝对不要碰的」为止」。")


def test_提示词开头那份平台清单必须等于产品能自动同步的那几个() -> None:
    """**提示词第一句就在替产品做声明**，而没有任何判据盯着它。

    `find_hardcoded_platform_claims.py` 只扫 5 个文件（扩展的 sidepanel、
    PWA 的三份、`docs/使用说明.md`），**HANDOFF.md 不在里面**——
    而 HANDOFF 首屏那段才是接手方唯一会整块读走的东西。

    2026-08-14 实测清单是对的（6 个名字对 6 个 `SYNCABLE_NOW`）。
    这道判据不是为了修它，是为了**下次 SYNCABLE_NOW 一改，这里当场红**。

    下面这张对照表是"提示词里用哪个名字称呼这个平台"。它和产品的
    `PLATFORM_LABELS` 不完全一样（`generic-web` 在产品里叫「通用网页」，
    界面卡片印「Chrome书签/网页」，而对普通人最认得的说法是「Chrome 书签」）——
    **名字可以不同，但覆盖必须一一对应**，所以下面先断言这张表的键
    正好等于 `SYNCABLE_NOW`。
    """
    import sys  # noqa: PLC0415
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from social_archive.account_sync import SYNCABLE_NOW  # noqa: PLC0415

    在提示词里怎么称呼 = {
        "bilibili": "B站",
        "douyin": "抖音",
        "xiaohongshu": "小红书",
        "reddit": "Reddit",
        "instagram": "Instagram",
        "generic-web": "Chrome 书签",
    }
    assert set(在提示词里怎么称呼) == set(SYNCABLE_NOW), (
        "这张对照表和 SYNCABLE_NOW 对不上了：\n"
        f"  表里有而产品没有：{sorted(set(在提示词里怎么称呼) - set(SYNCABLE_NOW))}\n"
        f"  产品有而表里没有：{sorted(set(SYNCABLE_NOW) - set(在提示词里怎么称呼))}\n"
        "  产品加/减了能自动同步的平台，就要同时改这张表和 HANDOFF 首屏那句。")

    prompt = _prompt_block()
    missing = [f"{pid}（{name}）" for pid, name in 在提示词里怎么称呼.items()
               if name not in prompt]
    assert not missing, (
        f"提示词开头那份清单漏了：{missing}\n"
        "  接手方会照它判断这个产品能做什么——漏一个，那个平台就等于不存在。")


def test_那两条红线自己得在提示词里() -> None:
    """**最贵的两条不能只靠一个指针。**

    它们是"破了才知道"的（一条产生真实账单，一条把登录态带出他的机器），
    所以必须直接出现在他一次粘贴就能带走的那段话里，而不是一个指针。
    """
    prompt = _prompt_block()
    for keyword, why in (
        ("InfrequentAccess", "R2 的 IA 存储类：从第 1 次操作起计费且按整单位向上取整"),
        ("HeadObject", "判存在的正确做法；整包下载来判断存在会烧掉免费额度"),
        ("Cookie", "国内平台的登录态不出他的浏览器"),
    ):
        assert keyword in prompt, (
            f"可粘提示词里没有 {keyword}——{why}。\n"
            "  这一条属于破了才知道的那种，不能只写成「去读第六节」。")
