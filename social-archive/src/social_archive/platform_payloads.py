"""平台自己的 API 响应体 → 我们的条目（v0.0.0.7 / T08）。

## 为什么是服务端解析

扩展只搬运，不 `JSON.parse`（background.js:1303 的原话：「解析失败会吞掉本来
能救的数据」）。原始字节到了服务端，解析失败还能留证、还能重放；在浏览器里
解析失败就是彻底没了。

## 这个模块存在的真正理由：**bilibili 的成功响应可以是空的**

2026-08-04 实测（不带任何 Cookie、不带登录态、纯 curl）：

    GET https://api.bilibili.com/x/v3/fav/resource/list?media_id=12&pn=1&ps=5&platform=web
    → HTTP 200
    → {"code":0,"message":"OK","ttl":1,"data":null}

试了四个 media_id（uid 1 / 2 / 208259 / 946974 的默认收藏夹），**全都是这个**。

也就是说：**HTTP 200、业务码 0、message "OK"、而 data 是 null。**

这正是 INV-NO-SILENT-ZERO 要防的形状，而且是最阴的一种——它不是错误码、
不是 4xx、不是异常。一个"照常理写"的解析器会做 `data.get("medias", [])`
拿到空列表，报告「同步成功，0 条」。用户看到的是「你没有收藏」，
而真相是「你没登录 / 这个收藏夹不公开」。v0.0.0.6 生产上"永远是 0"
就是这个形状（evidence/T00/CURRENT_TRUTH.json）。

所以这里的第一条规矩是：**`code == 0` 且 `data is None` 是失败，不是空。**

## 哪些是实测的，哪些不是

  实测（2026-08-04，四次独立请求）
    · 接口活着，HTTP 200
    · 信封形状 {code, message, ttl, data}
    · 匿名访问 → data 为 null

  **未实测**（来自 bilibili-API-collect 等公开文档，任务包三处互相印证）
    · data.medias[] 里每一项的字段名

未实测的部分不许静默降级：medias 非空却一条都映射不出来时**抛错**，
不返回空列表。宁可报「读到了但看不懂」，也不要报「你没有收藏」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class PayloadUnreadable(Exception):
    """响应体读不懂。带着一个失败码，让上层能给出中文原因而不是"同步成功 0 条"。"""

    def __init__(self, message_zh: str, failure_code: str) -> None:
        super().__init__(message_zh)
        self.message_zh = message_zh
        self.failure_code = failure_code


@dataclass(frozen=True)
class FavItem:
    """一条收藏。字段只留我们真的会写进库的那些。"""

    external_id: str
    url: str
    title: str
    author: str = ""
    cover_url: str = ""
    published_at: int | None = None
    favorited_at: int | None = None


def _envelope(body: str, platform_label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError) as exc:
        raise PayloadUnreadable(
            f"{platform_label}返回的内容不是能读懂的格式，这一次没有取到任何东西。",
            "PAYLOAD_NOT_JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise PayloadUnreadable(
            f"{platform_label}返回的内容不是预期的结构，这一次没有取到任何东西。",
            "PAYLOAD_NOT_JSON",
        )
    return parsed


def parse_bilibili_favlist(body: str) -> tuple[list[FavItem], bool]:
    """解析 B 站收藏夹一页。

    返回 `(条目, 还有下一页)`。

    任何读不出条目的情况都**抛 PayloadUnreadable**，绝不返回空列表——
    见模块文档最上面那段实测。
    """
    payload = _envelope(body, "B站")
    code = payload.get("code")

    if code != 0:
        # 平台自己说不行。把它的原话带上：它比我们编的更准。
        upstream = str(payload.get("message") or "").strip()
        detail = f"（B站说：{upstream}）" if upstream else ""
        if code in (-101, -400, 62002):
            raise PayloadUnreadable(
                f"B站说这个收藏夹现在读不到{detail}。多半是登录状态过期了，"
                "在浏览器里重新登录一次 B 站再试。",
                "NOT_LOGGED_IN",
            )
        raise PayloadUnreadable(
            f"B站拒绝了这次读取{detail}。这一次没有取到任何东西。",
            "PLATFORM_REFUSED",
        )

    data = payload.get("data")
    if data is None:
        # **实测形状。** code=0、message=OK、data=null。
        # 绝不能变成"0 条收藏"。
        raise PayloadUnreadable(
            "B站返回了成功，但没有给任何收藏内容——通常是这个浏览器还没登录 B 站，"
            "或者这个收藏夹不公开。**这不代表你没有收藏。**"
            "在浏览器里打开 B 站确认已登录，然后再同步一次。",
            "NOT_LOGGED_IN",
        )
    if not isinstance(data, dict):
        raise PayloadUnreadable(
            "B站返回的结构和预期不同，这一次没有取到任何东西。",
            "PAYLOAD_SHAPE_CHANGED",
        )

    medias = data.get("medias")
    if medias is None:
        raise PayloadUnreadable(
            "B站返回里没有收藏列表这一段，这一次没有取到任何东西。",
            "PAYLOAD_SHAPE_CHANGED",
        )
    if not isinstance(medias, list):
        raise PayloadUnreadable(
            "B站返回的收藏列表不是一个列表，这一次没有取到任何东西。",
            "PAYLOAD_SHAPE_CHANGED",
        )

    has_more = bool(data.get("has_more"))

    # 空列表是**合法的**：翻到最后一页、或这个收藏夹真的空。
    # 它与上面 data is None 的区别在于：那一个是"平台没告诉我们"，
    # 这一个是"平台明确说了：这里没有"。
    if not medias:
        return [], has_more

    items: list[FavItem] = []
    for media in medias:
        if not isinstance(media, dict):
            continue
        item = _bilibili_media_to_item(media)
        if item is not None:
            items.append(item)

    if not items:
        # **拿到了非空列表却一条都映射不出来。** 字段名变了，或者我们理解错了。
        # 这里返回空列表就等于把"看不懂"报成"没有"——本模块存在的全部理由。
        raise PayloadUnreadable(
            f"B站返回了 {len(medias)} 条收藏，但一条都没能读懂（字段和预期不一样）。"
            "已如实记为失败，不会假装同步成功。",
            "PAYLOAD_SHAPE_CHANGED",
        )
    return items, has_more


def _bilibili_media_to_item(media: dict[str, Any]) -> FavItem | None:
    """一条 media → FavItem。读不出链接的返回 None（由调用方汇总判断）。

    **字段名来自公开文档，未经真实响应验证**（见模块文档「哪些是实测的」）。
    所以这里对每个字段都用宽松取值，且允许返回 None——真正的守卫在调用方：
    非空列表全都映射不出来时抛错。
    """
    bvid = str(media.get("bvid") or "").strip()
    raw_id = media.get("id")
    link = str(media.get("link") or "").strip()

    if bvid:
        url = f"https://www.bilibili.com/video/{bvid}"
        external_id = bvid
    elif link.startswith("bilibili://video/"):
        # link 形如 bilibili://video/<aid>
        aid = link.rsplit("/", 1)[-1]
        if not aid.isdigit():
            return None
        url = f"https://www.bilibili.com/video/av{aid}"
        external_id = f"av{aid}"
    elif isinstance(raw_id, int):
        url = f"https://www.bilibili.com/video/av{raw_id}"
        external_id = f"av{raw_id}"
    else:
        return None

    def _int_or_none(value: Any) -> int | None:
        return value if isinstance(value, int) and value > 0 else None

    upper = media.get("upper")
    author = str(upper.get("name") or "").strip() if isinstance(upper, dict) else ""

    return FavItem(
        external_id=external_id,
        url=url,
        title=str(media.get("title") or "").strip(),
        author=author,
        cover_url=str(media.get("cover") or "").strip(),
        published_at=_int_or_none(media.get("pubtime")),
        favorited_at=_int_or_none(media.get("fav_time")),
    )
