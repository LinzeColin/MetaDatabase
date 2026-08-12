r"""把抓页面时抓重了的标题还原成真标题（2026-08-12）。

## 这一类坏标题长什么样

抖音的卡片上，播放数和标题挨着排。取数侧把这一块整个读了下来，于是存进来的是：

    23.0万极限三选一，你喜欢哪个？ #肉腿微胖 #肉腿ootd极限三选一，你喜欢哪个？ #肉腿微胖 #肉腿ootd
    └计数┘└──────────── 正文 ────────────┘└──────────── 正文又来一遍 ────────────┘

生产实测 11 条，全部是抖音。**它们不需要联网也不需要他登录就能修好**——
正文重复本身就是证据，把后一遍去掉、把计数去掉，剩下的就是真标题。

我上一轮说「抖音那些修不了，要 Owner 的登录态」，对**纯数字**那两条（`6.6万`、
`4.4万`）是真的，对这 11 条是**错的**：我当时那把判据只认「整串都是数字」，
这 11 条正文好端端地跟在计数后面，它一条都没看见。

## 为什么判据是「正文重复」而不是「以计数开头」

因为「以计数开头」会吃掉正当标题。生产库里就有一条：

    14万亿巨额放水+50万亿存款到期，微观体感寒冷，钱到底去哪了？

`14万亿` 是他要说的话，不是播放数。按「以计数开头」去掉前缀，剩下
`亿巨额放水+50万亿存款到期…`——把人家的标题啃掉一个字。

所以顺序反过来：**先看正文重不重复，重复了才说明前面那截计数是页面上的东西**。
不重复就一个字都不动，哪怕它以数字开头。

## 重复要占多大比例

一开始我写的是「结尾有 4 个字和开头一样就算重复」，立刻误伤了一条：

    老布探险原创的烈马等高线皮肤…… #烈马bronco #越野改装 #汽车贴膜 #老布探险
    ↑ 开头是「老布探险」                                        ↑ 结尾也是「老布探险」

那是标签，不是重复。真正重复的那 11 条，后一遍占整串的 **50%**（正正好一半），
而这条只占 6%。判据取 **40%** 作分界，两边差得很远，中间没有东西。
"""

from __future__ import annotations

import re

# 页面上贴在标题前面的播放数：`23.0万`、`1.6万`、`14亿`。
_COUNT_PREFIX = re.compile(r"^[\d.]+[万亿]")

# 后一遍至少要占正文的这么多，才算「重复」而不是「结尾恰好和开头撞了几个字」。
_REPEAT_MUST_COVER = 0.4

# 整串就是页面上的一个零件，正文一个字都没抓到——这一类**本地修不了**，
# 只能拿链接去外面查（B 站有公开接口，抖音没有）。
_PLAYBACK = re.compile(r"^\d{1,2}:\d{2}(?:/\d{1,2}:\d{2})?$")
_UI_LABEL = re.compile(r"^(?:已看完|正在看|未看完|稍后再看|已追完)$")
_ONLY_NUMBERS = re.compile(r"^[\d.:万亿\s]+$")


def is_all_chrome_no_title(value: str | None) -> bool:
    """整串都是页面零件，正文没抓到——`06:26/12:57`、`已看完`、`6.6万`、`646`。

    和 `undouble_title` 的分工：那个函数处理「正文抓到了，只是抓重了」，
    **本地就能修**；这个函数认的是「正文根本没抓到」，本地无从修起，
    得拿链接去外面查真标题。两类互斥，判据也各管各的。
    """
    text = (value or "").strip()
    if not text:
        return False
    return bool(_PLAYBACK.fullmatch(text) or _UI_LABEL.fullmatch(text)
                or _ONLY_NUMBERS.fullmatch(text))


def _drop_the_second_copy(body: str) -> str | None:
    """`正文正文` → `正文`；不是这个形状返回 None。

    形状是 `A + B`，其中 B 是 A 的前缀（整段重复时 B 就是 A 本身）。
    只在 B 占到整串 40% 以上时才认——见模块开头「重复要占多大比例」。
    """
    length = len(body)
    if length < 4:
        return None
    for split in range((length + 1) // 2, length):
        repeat = body[split:]
        if len(repeat) < _REPEAT_MUST_COVER * length:
            break                       # split 再大，repeat 只会更短
        if body[:split].startswith(repeat):
            return body[:split]
    return None


def undouble_title(value: str | None) -> str | None:
    """抓重了就还原成真标题，否则**原样返回**（包括原来的空白和 None）。

    两种摆法都认：计数前缀 + 重复正文，以及没有前缀的纯重复正文。
    两种都不是，就一个字都不改——这个函数只在能拿出证据时动手。
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return value

    without_count = _COUNT_PREFIX.sub("", text, count=1)
    if without_count != text:
        kept = _drop_the_second_copy(without_count)
        if kept:
            return kept.strip()

    kept = _drop_the_second_copy(text)
    if kept:
        return kept.strip()
    return value
