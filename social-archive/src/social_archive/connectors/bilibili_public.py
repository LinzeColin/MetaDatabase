"""B 站公开收藏夹的服务端读取（2026-08-17）。

## 为什么要有它

在此之前 B 站只有「浏览器会话」一条路：扩展在 Owner 的 Chrome 里打开页面、
读他的收藏。那条路要三样东西同时成立 —— Chrome 开着、平台登录态还在、
主机授权给过。**任何一样不成立就是零条**，而他实测的三次分别倒在：

    bilibili     BROWSER_SCAN_FAILED          页面打开了读不到
    douyin       PLATFORM_PERMISSION_MISSING  Chrome 授权没给到
    xiaohongshu  LIST_SHAPE_NOT_RECOGNISED    识别器认不出

2026-08-17 实测出一件此前没人问过的事：**他的 B 站收藏夹是公开的。**
拿他账号行里那个 uid（`https://space.bilibili.com/3493091105311656`）
去打 B 站公开接口，不带任何登录态：

    /x/v3/fav/folder/created/list-all?up_mid=…  → code 0，6 个夹子共 46 条
    /x/v3/fav/resource/list?media_id=…          → code 0，真标题真作者真 bvid

于是 B 站这条路可以整条搬到服务端：**不要浏览器、不要授权、不要 Chrome 开着**，
每 6 小时自己跑。这是他从「三个星期零条」到「有东西进来」的最短一条路。

## 边界（写清楚，免得被读成更大的承诺）

· **只读公开收藏夹。** 设为私密的夹子这条路读不到 —— 那种仍然要浏览器那条路。
  接口对私密夹返回 code≠0，这里如实报 `BILIBILI_FOLDER_NOT_VISIBLE`，不假装成零。
· **只读收藏夹**（`favorite`）。稍后再看、点赞是另外的接口，不在这里。
· 不带任何 Cookie。这条路**结构上不可能**碰到他的登录态 —— 那是这个产品的前提。
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

from .base import ConnectorResult

API = "https://api.bilibili.com"
#: B 站对没有 UA / Referer 的请求会限流甚至 -352。这不是绕过风控，
#: 是按它公开文档要求的方式自报身份。
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
_PAGE_SIZE = 20


def extract_uid(identity: str | None) -> str | None:
    """从账号行里那个字段取出 uid。

    实测他库里存的是整条空间地址 `https://space.bilibili.com/3493091105311656`，
    而不是裸数字 —— 直接拿去当 uid 会得到 code≠0，且错误信息毫无指向。
    """
    if not identity:
        return None
    match = re.search(r"(?:space\.bilibili\.com/)?(\d{4,})", str(identity))
    return match.group(1) if match else None


class BilibiliPublicConnector:
    connector_id = "bilibili"
    display_name = "B站"

    def __init__(self, identity: str | None) -> None:
        self.uid = extract_uid(identity)

    def health(self) -> dict[str, Any]:
        return {"connector_id": self.connector_id, "state": "connected" if self.uid else "blocked_environment",
                "detail": "" if self.uid else "账号行里读不出 B 站 uid"}

    # ── 游标 ───────────────────────────────────────────────────────
    # 形如 "3:2" = 第 3 个收藏夹的第 2 页。**用序号不用 media_id**：
    # 夹子被删掉时按 id 续跑会永远找不到它而卡住，按序号最多多读一页。

    @staticmethod
    def _parse_cursor(cursor: str | None) -> tuple[int, int]:
        if not cursor:
            return 0, 1
        try:
            folder_index, page = cursor.split(":", 1)
            return max(0, int(folder_index)), max(1, int(page))
        except (ValueError, AttributeError):
            return 0, 1

    def _get(self, client: httpx.Client, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = client.get(API + path, params=params, headers={
            "User-Agent": _UA,
            "Referer": f"https://space.bilibili.com/{self.uid}/favlist",
        })
        response.raise_for_status()
        return response.json()

    def fetch(self, relation: str, limit: int = 100, cursor: str | None = None) -> ConnectorResult:
        run_id = str(uuid.uuid4())
        if not self.uid:
            return ConnectorResult(
                self.connector_id, run_id, "blocked_environment",
                scan_receipt={"completeness": "unknown", "item_count": 0,
                              "failure_code": "BILIBILI_UID_UNKNOWN"},
                errors=[{"code": "BILIBILI_UID_UNKNOWN",
                         "message": "账号行里读不出 B 站 uid，服务端这条路走不了",
                         "retryable": False}])

        folder_index, page = self._parse_cursor(cursor)
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                listing = self._get(client, "/x/v3/fav/folder/created/list-all", {"up_mid": self.uid})
                if listing.get("code") != 0:
                    # **公开夹子一个都看不到，和「一条内容都没有」不是一回事。**
                    return ConnectorResult(
                        self.connector_id, run_id, "partial",
                        scan_receipt={"completeness": "unknown", "item_count": 0,
                                      "failure_code": "BILIBILI_FOLDER_NOT_VISIBLE",
                                      "relation_type": relation},
                        errors=[{"code": "BILIBILI_FOLDER_NOT_VISIBLE",
                                 "message": f"看不到公开收藏夹（B站 code={listing.get('code')}：{listing.get('message')}）。"
                                            "夹子设为私密时只能走浏览器那条路。",
                                 "retryable": False}])
                folders = ((listing.get("data") or {}).get("list")) or []
                if not folders:
                    return ConnectorResult(
                        self.connector_id, run_id, "success",
                        scan_receipt={"completeness": "complete", "item_count": 0,
                                      "relation_type": relation,
                                      "folder_count": 0})
                if folder_index >= len(folders):
                    return ConnectorResult(
                        self.connector_id, run_id, "success",
                        scan_receipt={"completeness": "complete", "item_count": 0,
                                      "relation_type": relation,
                                      "folder_count": len(folders)})

                folder = folders[folder_index]
                media_id = folder.get("id")
                detail = self._get(client, "/x/v3/fav/resource/list", {
                    "media_id": media_id, "pn": page,
                    "ps": min(max(int(limit) or _PAGE_SIZE, 1), _PAGE_SIZE),
                    "platform": "web",
                })
        except httpx.HTTPError as exc:
            return ConnectorResult(
                self.connector_id, run_id, "partial",
                scan_receipt={"completeness": "unknown", "item_count": 0,
                              "failure_code": "BILIBILI_API_FAILED",
                              "relation_type": relation,
                              **({"cursor_start": cursor} if cursor else {})},
                errors=[{"code": "BILIBILI_API_FAILED", "message": str(exc), "retryable": True}])

        if detail.get("code") != 0:
            return ConnectorResult(
                self.connector_id, run_id, "partial",
                scan_receipt={"completeness": "unknown", "item_count": 0,
                              "failure_code": "BILIBILI_FOLDER_NOT_VISIBLE",
                              "relation_type": relation},
                errors=[{"code": "BILIBILI_FOLDER_NOT_VISIBLE",
                         "message": f"这个收藏夹读不到（code={detail.get('code')}：{detail.get('message')}）",
                         "retryable": False}])

        data = detail.get("data") or {}
        medias = data.get("medias") or []
        info = data.get("info") or {}
        observations = []
        for media in medias:
            bvid = media.get("bvid") or media.get("bv_id")
            if not bvid:
                continue
            upper = media.get("upper") or {}
            observations.append({
                "relation_type": relation,
                "id": str(bvid),
                "bvid": bvid,
                "title": media.get("title"),
                "author_name": upper.get("name"),
                "collection_key": str(info.get("title") or ""),
            })

        # 这一夹还有下一页就翻页；没有就换下一夹。**两种都还没读完，
        # 所以回执一律 partial** —— 只有走到最后一夹的最后一页才算 complete。
        if data.get("has_more"):
            next_cursor: str | None = f"{folder_index}:{page + 1}"
        elif folder_index + 1 < len(folders):
            next_cursor = f"{folder_index + 1}:1"
        else:
            next_cursor = None

        receipt: dict[str, Any] = {
            "completeness": "complete" if next_cursor is None else "partial",
            "item_count": len(observations),
            "next_cursor": next_cursor,
            "relation_type": relation,
            "folder_count": len(folders),
            "folder_title": info.get("title"),
            "read_without_login": True,
        }
        if cursor:
            receipt["cursor_start"] = cursor
        return ConnectorResult(
            self.connector_id, run_id,
            "success" if next_cursor is None else "partial",
            observations=observations, scan_receipt=receipt)
