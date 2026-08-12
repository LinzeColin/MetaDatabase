r"""说明书里用「」引的那些整句，产品必须**现在还在这么说**（2026-08-13）。

## 为什么

说明书好几处**逐字引用屏幕上的话**，好让他能对上号，比如断开那一行：

    「账号已断开——点这一行的『连接账号』重新授权一次就会继续同步；
      已存下的 N 条一条不会少。」

产品那句改一个字，说明书就变成**在描述一个不存在的界面**——而验收第 2 条
写着「说明里写的每一步都必须被判据验过真的存在，**不许写愿景**」。
引一句产品已经不说的话，正是写愿景。

**在这条判据之前，没有任何东西比对过这些整句。** 已有的
`test_the_guide_only_names_things_that_exist.py` 查的是**名字**（按钮名、平台名），
不是整句；名字对得上而整句漂了，它一个字都不会说。

## 现在是全绿的

写这条时量过：说明书里 ≥8 字的「」引文共 **11 条，11 条产品里都找得到**。
**所以这条不是在修一个现存缺陷，是把它钉住。**

## 比对前要抹平两样，各有各的道理

1. **`『』` 当作 `「」`。** 中文里 `『』` 就是 `「」` 的合法嵌套写法，
   说明书把产品的「连接账号」嵌进外层引号时写成『连接账号』是**排版正确**的，
   不是漂移。不抹平就会去"修"一处本来就对的排版。
2. **空白全抹掉。** 说明书为了排版会在长句中间断行，产品那句是一整行。

## 逃生门

`NOT_A_PRODUCT_QUOTE` 里可以登记「这句「」不是引产品，是强调」——
**门槛是写下理由**，和这个仓其余几处例外一个规矩。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/使用说明.md"

# **说明书自己的副本必须排除。**（2026-08-13，两条反例同时变绿才发现）
#
# `apps/pwa/guide.html` 是 `build_guide_page.py` 从这份说明书**生成**的。
# 把它算进"产品"，这条判据就是**拿说明书跟它自己比**——恒绿。
# 实测：我把产品那句改成「重新登录」、又把「一条不会少」整个换掉，
# **两次 13 条断言全绿**。没有反例就交货的话，交出去的是一条永远不会红的判据。
# 同一个形状这个仓记过：两个 source_id 字面两处、实质一处。
EXCLUDE = {"apps/pwa/guide.html"}

# 产品里「他看得见的话」可能出现的地方。
PRODUCT_GLOBS = (
    ("apps/pwa", "*.js"), ("apps/pwa", "*.html"),
    ("apps/browser-extension", "*.js"), ("apps/browser-extension", "*.html"),
    ("src/social_archive", "*.py"),
    # **桌面那两个 `.command` 也是产品**：说明书让他双击
    # 「同步到 Obsidian.command」/「只补收藏到 Obsidian.command」，
    # 生成它们的是 `scripts/refresh_desktop_launcher.py`。
    # 第一版语料只收 apps/ 和 src/，于是把这两句判成"产品里没有"——
    # **语料划窄了，判据就会去指控一份没错的说明书。**
    ("scripts", "*.py"),
    ("scripts", "*.command"),
)

MIN_LENGTH = 8
MAX_LENGTH = 200
# 说明书用 `N` 占位那个**运行时才知道的数**（"已存下的 N 条一条不会少。"，
# 产品那句是 `${content_count}`）。**这是正确的写法**，不是漂移——
# 比对时把它当通配符：在它两侧切开，每一段都要在产品里找得到。
PLACEHOLDER = re.compile(r"(?<![A-Za-z])N(?![A-Za-z])")
# **还要按标点切。** 产品那句往往是**几段字符串拼出来的**：
#     `……重新授权一次就会继续同步；` + `已存下的 ${count} 条一条不会少。`
# 于是说明书里连续的那一串，在源码里**根本不连续**（中间隔着反引号和 `+`）。
# 拿散文比源码本来就是近似的；按标点切成小句，正好落在开发者断字符串的地方。
BREAKS = re.compile(r"[；。，、！？：]")
SEGMENT_MIN = 6

# 「这句不是引产品」——登记它，并写下理由。
NOT_A_PRODUCT_QUOTE: dict[str, str] = {
    # 这两句是**他库里当时的实况快照**，说明书拿它举例，不是屏幕上的话。
    # 数字会随他同步而变，钉住它反而会逼人去改说明书里一段本来就该是快照的话。
    # （「说明书别替他的数据说话」另有 test_the_guide_never_speaks_for_his_data.py 管。）
    "favorite 46 · like 69 · history 70 · saved 5 · watch_later 1 · manual_save 2":
        "他库里当时的关系分布快照，举例用，不是产品说的话",
    "你库里现在：观看历史 70 · 点赞 69 · 收藏 46 · 已保存 5 · 手动存的 2 · 稍后再看 1":
        "同上，中文版的同一份快照",
}


def _normalise(text: str) -> str:
    """`『』`→`「」`（合法嵌套写法），空白全抹掉（说明书会为排版断行）。"""
    return re.sub(r"\s+", "", text.replace("『", "「").replace("』", "」"))


def _product_text() -> str:
    parts = []
    for folder, pattern in PRODUCT_GLOBS:
        for path in sorted((ROOT / folder).rglob(pattern)):
            if str(path.relative_to(ROOT)) in EXCLUDE:
                continue
            parts.append(path.read_text(encoding="utf-8"))
    return _normalise("\n".join(parts))


def _guide_quotes() -> list[str]:
    """**引文允许跨行。**（2026-08-13，第一版就漏在这儿）

    第一版正则写的是 `[^「」\n]`——不许跨行。而说明书里最要紧的那一句
    （断开那一行）正好是断成两行排的，于是它**从来没有被查过**：
    我把产品那句改一个字做反例，12 条断言一条都没红。
    **自检那一条当场把这个漏洞打红了**，否则我会带着一个查不到东西的判据交货。
    """
    text = GUIDE.read_text(encoding="utf-8")
    found = re.findall(rf"「([^「」]{{{MIN_LENGTH},{MAX_LENGTH}}})」", text, re.S)
    # 跨段落的多半不是一句引文，是两处引号凑巧配上了
    return [q for q in found if "\n\n" not in q and q not in NOT_A_PRODUCT_QUOTE]


def _segments(quote: str) -> list[str]:
    """按占位符切开，只留够长的那几段（太短的碎片随处可见，比了等于没比）。"""
    pieces: list[str] = []
    for part in PLACEHOLDER.split(quote):
        pieces.extend(BREAKS.split(part))
    return [s for s in (_normalise(piece) for piece in pieces)
            if len(s) >= SEGMENT_MIN]


def test_the_scan_actually_finds_quotes() -> None:
    """**先证明这把尺子量得到东西。**

    引号换一种写法、正则少一个花括号，`_guide_quotes()` 就会返回空表，
    然后下面每一条都空过——一个永远不会红的判据比没有判据更糟。
    这个仓当天已经因为同一个理由给另外两条判据加过自检。
    """
    quotes = _guide_quotes()
    assert len(quotes) >= 8, f"只扫到 {len(quotes)} 条引文，正则多半没匹配上"
    assert any("账号已断开" in q for q in quotes), \
        f"没扫到断开那一行的引文，取的地方不对：{quotes[:3]}"
    assert len(_product_text()) > 100_000, "产品源码没读到，比对会恒真"


@pytest.mark.parametrize("quote", _guide_quotes())
def test_每一句引文产品现在还在说(quote: str) -> None:
    product = _product_text()
    missing = [s for s in _segments(quote) if s not in product]
    assert not missing, (
        f"说明书引了这一句，而产品里现在找不到它：\n    「{quote}」\n"
        f"对不上的片段：{missing}\n"
        f"**要么产品那句改了、说明书没跟上（他会对着屏幕找一句不存在的话），"
        f"要么这句本来就不是引产品**——后者请登记进 NOT_A_PRODUCT_QUOTE 并写下理由。")
