"""读平台官方的「下载我的数据」压缩包（v0.0.0.21）。

## 为什么这条路才是「多平台」的正解

Owner 2026-08-06 的原话：

    「你跑了50+小时只做了一个平台？…不是有很多成熟现成的项目吗，
      那过来直接用，链接聚合不就好了」

他说得对，而我之前的做法错在**一个一个去逆向平台接口**。B 站能成，是因为
它的收藏夹接口恰好是公开无签名的 REST——**那是运气，不是方法**。
小红书、抖音、快手的收藏接口都有签名，逆向出来的东西今天能用明天就坏，
而且没有任何免费成熟项目替你做这件事（Karakeep / Linkwarden 这类是
**书签管理器**，它们同样读不了你的小红书收藏夹）。

真正成熟、免费、稳定、每个平台都提供的那条路是：**官方数据导出**。

    抖音      设置 → 账号与安全 → 个人信息下载
    小红书    设置 → 账号与安全 → 个人信息下载
    X         设置 → 下载你的数据存档
    Reddit    设置 → 请求你的数据
    Instagram 设置 → 下载你的信息
    YouTube   Google Takeout

那是平台自己给的、完整的、不会因为接口改版而坏掉的东西。
**一个导入器一次覆盖七个平台**，比逆向七次快得多也稳得多。

## 这个模块怎么读

不按平台写死格式——**按数据形状认**。官方包的实际形状就那么几种：

  · Netscape HTML 书签（`<A HREF="…">`）—— 浏览器与很多服务都导出这个
  · CSV，其中一列是链接 —— Reddit 的导出就是
  · JSON 数组／嵌套对象，字段里有 url / link / permalink
  · JS 包着的 JSON —— X 的存档是 `window.YTD.like.part0 = [ … ]`

## 三条不许违反的规矩

1. **不许静默跳过。** 每个文件都要出现在回执里，读懂了几条、没读懂为什么。
   一个只报「成功导入 N 条」而不说「另外 M 个文件没看懂」的导入器，
   会让人以为东西都进来了。
2. **一条都没读到 = 失败**，不是「成功，0 条」（INV-NO-SILENT-ZERO）。
3. **不猜平台。** 认不出来就老实说认不出来，由调用方给 platform_hint。
"""

from __future__ import annotations

import csv
import io
import json
import re
import re
import zipfile

import yaml
from typing import Any

# 一个条目至少要有的东西：能打开的网址。
URL_KEYS = ("url", "link", "permalink", "href", "expanded_url", "canonical_url",
            "webpage_url", "share_url", "note_url")
TITLE_KEYS = ("title", "name", "text", "full_text", "desc", "description", "caption")
TIME_KEYS = ("created_at", "created_utc", "timestamp", "time", "date", "add_date",
             "fav_time", "saved_at",
              # bilibili-cli 的清单用 pubdate / ctime 记时间
              "pubdate", "ctime", "fav_time")

HTTP = re.compile(r"https?://[^\s\"'<>\\]+")
# Netscape 书签：<A HREF="…" ADD_DATE="…">标题</A>
BOOKMARK = re.compile(
    r'<a\s+[^>]*href="(?P<url>https?://[^"]+)"(?P<attrs>[^>]*)>(?P<title>.*?)</a>',
    re.I | re.S)
ADD_DATE = re.compile(r'add_date="(\d+)"', re.I)
# X 的存档：window.YTD.like.part0 = [ … ]
JS_WRAPPED = re.compile(r"^\s*window\.[\w.]+\s*=\s*", re.S)

# 压缩包里不值得看的东西。**列在这里的会出现在回执里**，不是悄悄丢掉。
SKIP_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mov", ".webp", ".heic",
                 ".mp3", ".m4a", ".zip", ".ico", ".svg", ".woff", ".woff2", ".ttf",
                 ".css", ".map")
MAX_FILE_BYTES = 64 * 1024 * 1024


def _clean_title(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(raw or ""))
    text = re.sub(r"&(amp|lt|gt|quot|#39);", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:2048]


def _first(payload: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, "", []):
            return payload[key]
    # 官方包常把东西套一层（{"tweet": {...}} / {"data": {...}}）
    for value in payload.values():
        if isinstance(value, dict):
            found = _first(value, keys)
            if found not in (None, "", []):
                return found
    return None


def _records_from_object(payload: Any) -> list[dict]:
    """从任意 JSON 结构里挖出「带网址的条目」。"""
    out: list[dict] = []
    if isinstance(payload, list):
        for item in payload:
            out.extend(_records_from_object(item))
        return out
    if not isinstance(payload, dict):
        return out
    url = _first(payload, URL_KEYS)
    # **有些清单里根本没有网址，只有编号。**
    #
    # bilibili-cli 这类工具导出的条目通常长这样：
    #     {bvid: BV1xx…, title: …, owner: {name: …}, pubdate: …}
    # 一个 url 字段都没有。上面那条按 url 找的路径会整份漏掉，
    # 而它明明是一份完整、干净、他自己导出来的收藏清单。
    #
    # 这两个模板**不是我现编的**：仓里 registry.py:436 与
    # platform_payloads.py:184/191 早就在用同一份写法。
    # 顺序也和按形状读那条路一致：**取来的优先于拼来的**——
    # 只有在条目自己说不出网址时才拼。
    if not (isinstance(url, str) and HTTP.match(url)):
        bvid = _first(payload, ("bvid", "bv_id", "bvId"))
        aid = _first(payload, ("aid", "av_id", "avid"))
        if isinstance(bvid, str) and re.fullmatch(r"BV[0-9A-Za-z]{8,12}", bvid.strip()):
            url = f"https://www.bilibili.com/video/{bvid.strip()}"
        elif isinstance(aid, (int, str)) and str(aid).strip().isdigit():
            url = f"https://www.bilibili.com/video/av{str(aid).strip()}"
    if isinstance(url, str) and HTTP.match(url):
        out.append({
            "url": url,
            "title": _clean_title(_first(payload, TITLE_KEYS) or ""),
            "observed_at": _first(payload, TIME_KEYS),
        })
        return out
    # 没有 url 的对象：往下挖一层，官方包常把列表藏在某个键里
    for value in payload.values():
        if isinstance(value, (list, dict)):
            out.extend(_records_from_object(value))
    return out


def _read_html(text: str) -> list[dict]:
    out: list[dict] = []
    for match in BOOKMARK.finditer(text):
        stamp = ADD_DATE.search(match.group("attrs") or "")
        out.append({
            "url": match.group("url"),
            "title": _clean_title(match.group("title")),
            "observed_at": stamp.group(1) if stamp else None,
        })
    return out


def _read_csv(text: str) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except (csv.Error, ValueError):
        return []
    out: list[dict] = []
    for row in rows:
        clean = {str(k or "").strip().lower(): v for k, v in row.items() if k}
        found = _records_from_object(clean)
        out.extend(found)
    return out


def _read_yaml(text: str) -> list[dict]:
    """读 YAML 清单（bilibili-cli 这类工具的默认输出之一）。

    Owner 的项目表里 bilibili-cli 的角色是「JSON/YAML 导入」。
    JSON 那一半本来就走 `_read_json`；YAML 这一半此前**完全没有**——
    上传一个 .yaml 会掉进最后那个兜底（正则捡链接），
    而 bilibili-cli 的条目里连链接都没有，于是回执是「读不出任何链接」。

    只认安全子集（`safe_load`），不执行任何标签。
    """
    stripped = text.strip()
    # 一份 JSON 也是合法 YAML；让 JSON 走它自己那条路，回执里的形状名才准。
    if not stripped or stripped[0] in "[{":
        return []
    try:
        payload = yaml.safe_load(stripped)
    except yaml.YAMLError:
        return []
    if payload is None:
        return []
    return _records_from_object(payload)


def _read_json(text: str) -> list[dict]:
    stripped = JS_WRAPPED.sub("", text.strip())
    stripped = stripped.rstrip(";").strip()
    try:
        payload = json.loads(stripped)
    except ValueError:
        return []
    return _records_from_object(payload)


def _read_one(name: str, blob: bytes) -> tuple[list[dict], str]:
    """读一个文件。返回（条目, 说明）——**说明永远非空**，好让回执说得出话。"""
    lower = name.lower()
    if lower.endswith(SKIP_SUFFIXES):
        return [], "跳过：是媒体或样式文件，不含链接清单"
    if len(blob) > MAX_FILE_BYTES:
        return [], f"跳过：{len(blob) // (1024 * 1024)} MiB，超过单文件上限"
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = blob.decode("utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            return [], "跳过：不是文本，解码不了"
    for reader, shape in ((_read_json, "JSON"), (_read_html, "HTML 书签"),
                          (_read_csv, "CSV"), (_read_yaml, "YAML")):
        found = reader(text)
        if found:
            return found, f"按 {shape} 读到 {len(found)} 条"
    # 兜底：文本里裸的链接。**明说是兜底**，别让人以为它读懂了结构。
    urls = list(dict.fromkeys(HTTP.findall(text)))[:5000]
    if urls:
        return ([{"url": item, "title": "", "observed_at": None} for item in urls],
                f"没认出结构，只把文本里的 {len(urls)} 个链接捡了出来")
    return [], "读不出任何链接"


def read_export_archive(payload: bytes, *, limit: int = 10000,
                        filename: str = "") -> dict[str, Any]:
    """读一个官方数据导出包。

    **回执里每个文件都有一行**，读懂了几条、没读懂为什么——
    只报总数的话，「另外 30 个文件没看懂」就消失了。
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        # **不是压缩包，就当成一个文件来读。**
        #
        # Owner 的项目表里 bilibili-cli 的角色是「JSON/YAML 导入」，
        # 而那类工具吐出来的就是**一个裸文件**，不是压缩包。
        # 原来这里一律回「这不是一个能打开的压缩包」——
        # 也就是说那条导入路对他手上真实的文件**从入口就关着**。
        found, note = _read_one(filename or "上传的文件", payload)
        items: list[dict] = []
        seen: set[str] = set()
        for record in found:
            url = str(record.get("url") or "")
            if url and url not in seen:
                seen.add(url)
                items.append(record)
            if len(items) >= limit:
                break
        name = filename or "上传的文件"
        if not items:
            return {"ok": False, "failure_code": "FILE_HAS_NO_LINKS",
                    "error": f"这个文件里没有找到任何条目（{note}）。"
                             "如果它是压缩包，请确认没有被解压过；"
                             "如果是清单文件，请确认里面是导出的条目而不是配置。",
                    "files": [{"name": name, "found": 0, "new": 0, "note": note}],
                    "items": []}
        return {"ok": True,
                "files": [{"name": name, "found": len(found), "new": len(items),
                           "note": f"{note}（按单个文件读的，不是压缩包）"}],
                "items": items, "counted": len(items), "file_count": 1}

    files: list[dict] = []
    items: list[dict] = []
    seen: set[str] = set()
    for info in archive.infolist():
        if info.is_dir():
            continue
        try:
            blob = archive.read(info)
        except (KeyError, RuntimeError, zipfile.BadZipFile) as error:
            files.append({"name": info.filename, "found": 0,
                          "note": f"读不出来：{error.__class__.__name__}"})
            continue
        found, note = _read_one(info.filename, blob)
        fresh = 0
        for record in found:
            url = str(record.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            items.append(record)
            fresh += 1
            if len(items) >= limit:
                break
        files.append({"name": info.filename, "found": len(found),
                      "new": fresh, "note": note})
        if len(items) >= limit:
            files.append({"name": "(已达上限)", "found": 0, "new": 0,
                          "note": f"到 {limit} 条上限就停了——没读完，剩下的没看"})
            break

    if not items:
        # **一条都没读到不是「成功，0 条」。**
        unreadable = [item["name"] for item in files if not item.get("found")][:5]
        return {"ok": False, "failure_code": "EXPORT_HAS_NO_LINKS",
                "error": ("这个包里没有找到任何链接。可能是选了不含收藏/书签的导出范围，"
                          "或者上传的不是平台给的那个原始包。"),
                "files": files, "items": [],
                "unreadable_examples": unreadable}
    return {"ok": True, "files": files, "items": items,
            "counted": len(items), "file_count": len(files)}
