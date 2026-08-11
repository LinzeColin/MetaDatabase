#!/usr/bin/env python3
r"""前端资产的缓存戳，由**内容**算出来（2026-08-11）。

## 为什么从「跟着版本号」再往前走一步

0.0.0.30 把 `?v=007-r2` 那个写死的常量改成了跟着 `VERSION` 走。那修好了
「戳永远不动」，但留下一扇同形状的后门：**改了 `apps/pwa/` 却忘了升版**——
戳不动，Cloudflare 照样把旧文件回给他，最长 4 小时。
（`apps/browser-extension/` 有一条「改了就必须升版」的判据，`apps/pwa/` 没有。）

内容派生的戳没有这扇门：**改了内容，戳必然变；忘不掉，也糊弄不了。**
这个做法是「OVH VPS 库存监控脚本迁移」那个会话先落地的（`?v=<sha256前8位>`），
这里照同一个思路做，并把校验做成可跑的 `--check`。

## 为什么源站设 Cache-Control 没用（实测）

    源站（在生产机上打回环 127.0.0.1:18765）
        HTTP/1.1 200 OK        ← **一个 cache-control 都没有**
    公网（经 Cloudflare）
        cache-control: max-age=14400
        cf-cache-status: EXPIRED

**是 Cloudflare 的 Browser Cache TTL 给加上的 4 小时**，源站怎么设都会被盖掉
（另一个会话在他们的 zone 上量到的是源站 `no-cache` 被覆盖，同一形态）。
所以换缓存键是唯一可靠的手段——戳必须永远正确，不能靠人记得。

首页本身是 `cf-cache-status: DYNAMIC`（CF 默认不缓存 HTML），
所以他每次都拿到新的 HTML，戳一变就必然回源。

## 怎么算，以及为什么这样算

一个戳管全部资产（和 SW 缓存名同一个粒度，改一处全部换代，简单且不会漏）：

    STAMP = sha256( 按文件名排序拼接的「去掉戳之后」的内容 )[:8]

「去掉戳之后」是关键：`app.js` 里写着 SW 的地址、`sw.js` 里写着预缓存清单，
它们都含戳。**先把所有 `?v=…` 归一成 `?v=`再哈希**，否则写进去的戳会改变
下一次算出来的戳，永远收敛不了。

## 它写哪几处

    apps/pwa/index.html   每个 /assets/… 的 ?v=
    apps/pwa/sw.js        const CACHE = "social-archive-ui-<戳>" 与预缓存清单
    apps/pwa/app.js       navigator.serviceWorker.register("/assets/sw.js?v=<戳>")
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PWA = ROOT / "apps/pwa"
# 参与哈希的文件：首页引的那几个 + sw.js 自己。
# **不写死清单**：首页引到谁就算谁，新增一个资产自动进来。
CACHE_NAME = re.compile(r'const CACHE = "social-archive-ui-([^"]+)";')
STAMP_IN_URL = re.compile(r"\?v=[^\"'\s>)]*")


def _referenced_assets() -> list[str]:
    html = (PWA / "index.html").read_text(encoding="utf-8")
    names = {ref.split("?")[0][len("/assets/"):]
             for ref in re.findall(r"""(?:src|href)=["'](/assets/[^"']+)""", html)}
    names.add("sw.js")
    missing = [name for name in sorted(names) if not (PWA / name).is_file()]
    if missing:
        raise SystemExit(json.dumps(
            {"status": "FAIL", "error_code": "ASSET_REFERENCED_BUT_MISSING",
             "missing": missing,
             "message_zh": "首页引了一个磁盘上没有的资产——先修这个，别打戳"},
            ensure_ascii=False))
    return sorted(names)


def compute_stamp() -> tuple[str, list[str]]:
    """按「去掉戳之后」的内容算一个戳。

    不归一化的话：写进去的戳会改变文件内容 → 下次算出来的戳又不一样 → 永远不收敛。
    """
    names = _referenced_assets()
    digest = hashlib.sha256()
    for name in names:
        raw = (PWA / name).read_text(encoding="utf-8")
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(STAMP_IN_URL.sub("?v=", CACHE_NAME.sub(
            'const CACHE = "social-archive-ui-";', raw)).encode())
        digest.update(b"\0")
    return digest.hexdigest()[:8], names


def _restamp(text: str, stamp: str) -> str:
    text = STAMP_IN_URL.sub(f"?v={stamp}", text)
    return CACHE_NAME.sub(f'const CACHE = "social-archive-ui-{stamp}";', text)


def current_stamps() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name in ("index.html", "sw.js", "app.js"):
        raw = (PWA / name).read_text(encoding="utf-8")
        stamps = sorted({s[len("?v="):] for s in STAMP_IN_URL.findall(raw)})
        cache = CACHE_NAME.search(raw)
        if cache:
            stamps = sorted(set(stamps) | {cache.group(1)})
        found[name] = stamps
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="给前端资产打内容派生的缓存戳")
    parser.add_argument("--check", action="store_true",
                        help="只核对，不改；对不上就退 1")
    args = parser.parse_args()

    stamp, names = compute_stamp()
    before = current_stamps()
    wrong = {name: got for name, got in before.items() if got not in ([stamp], [])}
    empty = [name for name, got in before.items() if not got]

    if args.check:
        problems = []
        if empty:
            problems.append(f"{empty} 里一个戳都没有——那几个资产的更新到不了他浏览器")
        if wrong:
            problems.append(f"戳和内容对不上：{wrong}，按内容算应该是 {stamp}"
                            "（改完资产要重新跑 scripts/stamp_pwa_assets.py）")
        print(json.dumps({
            "status": "FAIL" if problems else "PASS",
            "stamp_from_content": stamp, "hashed_files": names,
            "stamps_in_files": before, "problems": problems,
            "why_zh": "Cloudflare 给 /assets/* 加 max-age=14400 且源站的头会被它盖掉，"
                      "换缓存键是唯一可靠的手段——戳必须永远等于内容的哈希。",
        }, ensure_ascii=False, indent=2))
        return 1 if problems else 0

    changed = []
    for name in ("index.html", "sw.js", "app.js"):
        path = PWA / name
        raw = path.read_text(encoding="utf-8")
        updated = _restamp(raw, stamp)
        if updated != raw:
            path.write_text(updated, encoding="utf-8")
            changed.append(name)
    print(json.dumps({"status": "PASS", "stamp": stamp, "changed": changed,
                      "hashed_files": names}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
