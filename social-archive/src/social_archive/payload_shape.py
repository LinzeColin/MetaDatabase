r"""读不懂一条响应时，把它的**字段骨架**记下来——只记名字，不记值（2026-08-12）。

## 为什么需要这个

Owner 按那颗诊断按钮，是为了让我知道**该盯哪个地址**。但地址只解决一半：
拿到地址之后，服务端还得**读得懂**那个响应，而现在只有 B 站有解析器
（`PAYLOAD_PARSERS = {"bilibili": …}`）。

也就是说，他按完那一下，我会拿到抖音的地址，然后发现自己**还是写不出解析器**
——因为我不知道抖音的响应长什么样。诊断上报**故意不送响应体**（那里面可能有
平台返回的个人信息），所以我得回头请他再做第二件事。

**让他按第二次，就是这个项目一直在拔的那种东西。**

## 这个模块做什么

响应体本来就会到他自己的服务器（`/v1/extension/captures/parse` 收的就是它，
只是读完就丢）。读不懂的时候，把那一条的**结构**抽出来记进诊断台账：

    顶层有哪几个键、哪个键下面是数组、数组里第一项有哪几个键、每个键是什么类型

**只有名字、类型、长度，一个值都不记。** 字段名是平台的接口约定，不是他的内容。

有了骨架，我就能照着写解析器——他那一下够了，不用再来一次。

## 硬边界

- **绝不记录值。** 字符串只记长度，数字只记 `"number"`，不记它是多少。
- 深度封顶 4 层、每层键封顶 40 个、数组只看第一项——响应可能很大，
  骨架不该跟着大。
- 键名本身封顶 80 字符（防止某些平台把内容塞进键名里）。
"""

from __future__ import annotations

import json
from typing import Any

MAX_DEPTH = 4
MAX_KEYS = 40
MAX_KEY_LENGTH = 80


def _describe(value: Any, depth: int) -> Any:
    """把一个值换成它的**形状**。名字、类型、长度——没有值。"""
    if depth > MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        shape: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_KEYS:
                shape["…"] = f"还有 {len(value) - MAX_KEYS} 个键"
                break
            shape[str(key)[:MAX_KEY_LENGTH]] = _describe(item, depth + 1)
        return shape
    if isinstance(value, list):
        if not value:
            return "array(0)"
        # **只看第一项。** 列表里每一项形状一样，看一项就够；
        # 看全部只会让骨架跟着响应一起大。
        return [f"array({len(value)}) of", _describe(value[0], depth + 1)]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        # **只记长度。** 标题、作者名、链接都在这一档里，一个字都不能带出去。
        return f"string(len={len(value)})"
    if value is None:
        return "null"
    return type(value).__name__


def sketch(body: str) -> dict[str, Any]:
    """一条响应的字段骨架。读不成 JSON 就说清楚，不猜。

    返回的东西**可以安全落盘**：里面没有任何来自平台的值。
    """
    text = (body or "").strip()
    if not text:
        return {"readable_as_json": False, "why": "响应体是空的"}
    try:
        parsed = json.loads(text)
    except ValueError as error:
        return {
            "readable_as_json": False,
            "why": f"不是 JSON（{error.__class__.__name__}）",
            "first_bytes_are_html": text[:1].lower() == "<",
            "length": len(text),
        }
    return {"readable_as_json": True, "length": len(text), "shape": _describe(parsed, 0)}
