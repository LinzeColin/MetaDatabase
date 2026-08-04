#!/usr/bin/env python3
"""抓到即固化：把诊断报告里读得懂的那个地址，变成拦截前缀（v0.0.0.7 / T09）。

## 为什么要有它

Owner 按一次诊断，报告自己落到他的服务器上（`diagnostics/extension-diagnostics.jsonl`）。
在此之前**没有任何东西读那份报告**——那正是「建好了没接上」的第十处：
写进去了，没人取出来。

这个脚本把那一步接上：读报告 → 取出**读得懂的那条**的地址 → 推出前缀 →
（`--apply`）写进 `content/platform-catalog.js` 的 INTERCEPT_PREFIXES。

## 它拒绝做什么

平台目录里那段注释写着「没实测过的一律写 null，而不是写一个看着像的」，
这个脚本必须守住同一条线：

  · **没有 readable_urls 就拒绝。** 只有「拦到了」而没有「读得懂」，
    说明我们并不知道哪一条才是收藏列表接口——那时写进去的就是「看着像的」。
  · **推不出足够具体的前缀就拒绝。** 诊断模式的前缀是从域名推的
    （比如 `bilibili.com`），页面上每个请求都会被抓。如果读得懂的那几条
    只能收敛到一个域名，那不是前缀，是「拦下所有东西」——装上去等于没装。
  · **不猜。** 多条读得懂时取它们的公共路径前缀；公共部分退化到域名就拒绝。

## 用法

    # 看看会写什么，不动文件
    python3 scripts/freeze_intercept_prefix.py --platform bilibili \\
        --report /var/lib/social-archive/diagnostics/extension-diagnostics.jsonl

    # 确认无误再写
    ... --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "apps/browser-extension/content/platform-catalog.js"


def _fail(code: str, message: str, **extra) -> int:
    print(json.dumps({"status": "REFUSED", "error_code": code, "message_zh": message, **extra},
                     ensure_ascii=False))
    return 4


def _prefix_of(url: str) -> str:
    """`https://api.bilibili.com/x/v3/fav/resource/list?pn=1` → `api.bilibili.com/x/v3/fav/resource/list`"""
    parts = urlsplit(url)
    host = parts.netloc.split("@")[-1]
    return f"{host}{parts.path}".rstrip("/")


def _common_prefix(prefixes: list[str]) -> str:
    """多条读得懂时取公共**路径段**前缀——按 `/` 切，不按字符切。

    按字符切会切出 `api.bilibili.com/x/v3/fav/resou` 这种半截路径段，
    看着像个前缀，实际匹配行为完全不可预期。
    """
    split = [p.split("/") for p in prefixes]
    common: list[str] = []
    for segments in zip(*split):
        if len(set(segments)) != 1:
            break
        common.append(segments[0])
    return "/".join(common)


def main() -> int:
    parser = argparse.ArgumentParser(description="把诊断报告里读得懂的地址固化成拦截前缀")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--report", required=True, help="extension-diagnostics.jsonl")
    parser.add_argument("--apply", action="store_true", help="真的写进平台目录")
    parser.add_argument("--catalog", default=str(CATALOG))
    args = parser.parse_args()

    report = Path(args.report).expanduser()
    if not report.is_file():
        return _fail("REPORT_MISSING", f"读不到诊断报告：{report}")

    platform = args.platform.strip().lower()
    entries = []
    for line in report.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue                        # 半截行不算证据，跳过而不是崩
        if str(row.get("platform", "")).lower() == platform:
            entries.append(row)
    if not entries:
        return _fail("NO_DIAGNOSTIC_FOR_PLATFORM",
                     f"报告里没有 {platform} 的诊断记录——先让 Owner 在那个平台的收藏页按一次诊断。")

    usable = [e for e in entries if e.get("readable_urls")]
    if not usable:
        return _fail(
            "NOTHING_READABLE",
            f"{platform} 有 {len(entries)} 条诊断记录，但**没有一条读得懂**。"
            "只知道「拦到了」而不知道哪一条是收藏列表接口，这时候写进去的就是"
            "「看着像的」——平台目录明确不许那样做。",
            diagnostics_seen=len(entries),
        )

    latest = usable[-1]
    prefixes = sorted({_prefix_of(u) for u in latest["readable_urls"] if u})
    if not prefixes:
        return _fail("READABLE_URLS_EMPTY", "读得懂的地址列表是空的。")
    candidate = prefixes[0] if len(prefixes) == 1 else _common_prefix(prefixes)

    # 前缀必须比「一个域名」更具体，否则等于拦下页面上的所有请求。
    if "/" not in candidate or not candidate.split("/", 1)[1]:
        return _fail(
            "PREFIX_TOO_BROAD",
            f"推出来的前缀是 {candidate!r}——只到域名。那不是前缀，是「拦下所有东西」，"
            "装上去等于没装。多按几次诊断、或换一个收藏夹再试。",
            readable_urls=latest["readable_urls"],
        )

    result = {
        "status": "READY",
        "platform": platform,
        "prefix": candidate,
        "derived_from": latest["readable_urls"],
        "diagnostic_at": latest.get("at"),
        "applied": False,
    }

    if args.apply:
        catalog_path = Path(args.catalog)
        text = catalog_path.read_text(encoding="utf-8")
        pattern = re.compile(rf"(\n\s*{re.escape(platform)}:\s*)(null|Object\.freeze\(\[[^\]]*\]\))")
        if not pattern.search(text):
            return _fail("PLATFORM_NOT_IN_CATALOG",
                         f"平台目录的 INTERCEPT_PREFIXES 里没有 {platform} 这一项。")
        replacement = rf'\g<1>Object.freeze(["{candidate}"])'
        catalog_path.write_text(pattern.sub(replacement, text, count=1), encoding="utf-8")
        result["applied"] = True
        result["catalog"] = str(catalog_path)
        result["reminder"] = (
            "写进去了，但**今天还没有任何东西会去用它**。实测（2026-08-05）："
            "整个仓里只有 background.js 的 installNetObserverForTab 读这张表，"
            "而唯一的调用方是弹窗的诊断按钮（diagnostic=true），那条路进门第一件事"
            "就是把读到的前缀**整个覆盖掉**，改用当前页域名推出来的。"
            "没有任何地方以 diagnostic=false 调它。"
            "\n所以固化是必要的一步，但不是最后一步：**让同步真的用上这个前缀是 T10/T11**，"
            "那一格还没做。别把「写进去了」当成「能同步了」。"
        )

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
