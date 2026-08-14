#!/usr/bin/env python3
r"""包里有没有它**运行时才去取**的那些文件（2026-08-14）。

## 已经有的两道盖不住这一档

1. `check_the_shipped_package_is_the_committed_code.py`
   比的是「zip 里那 27 个文件」对「git HEAD 里同名的那 27 个」。
   **它的比较集是「包里有的文件」**——少打包一个，27/27 照样全对。
2. `shipped_package_drill.py` 把 zip 解出来真装进 Chrome。
   Chrome 装载时确实会拒绝 manifest 指向的缺失文件
   （`content_scripts` / `background.service_worker` / 图标 / `web_accessible_resources`）。

**而运行时那一档两道都看不见。** 2026-08-14 实测 `background.js`：

    content/bilibili-reader.js   executeScript 注入   manifest 里没提过
    content/extract-core.js      executeScript 注入   manifest 里没提过
    content/extract.js           executeScript 注入   manifest 里没提过
    content/fab.js               executeScript 注入   manifest 里没提过
    content/net-relay.js         executeScript 注入   manifest 里没提过
    net-observer.js              executeScript 注入   manifest 里没提过

manifest 里没有这些名字，所以 Chrome 装载期**结构上不可能**校验它们。
把 `content/bilibili-reader.js` 改个名：打包成功、zip 对得上 git、
Chrome 装得上、service worker 起得来、23 个演练全绿——
而唯一跑通的那条 B 站读取路在他按下去那一刻才炸。

这正是这个仓反复付代价的那个形状：**判据扫的集合比实况小**。
上一次是「没人打开过最终那个 zip」，这次是「打开了，但只数了里面有的」。

## 口径

· 真源是**最终那个 zip**，不是 `apps/browser-extension/` 源码目录。
  （`--url` 还能直接拉线上那份——他点下载拿到的就是它。）
· 引用从五处取：`executeScript({files:[…]})`、`runtime.getURL(…)`、
  `importScripts(…)`、`import … from "…"`、HTML 的 `<script src>` / `<link href>`。
· 相对路径按**引用者所在目录**解析（`content/` 下的文件引同目录的邻居）。
· 外链、`data:`、带 `*` 的模式一律不管——那些不是包内文件。
· **空扫要当失败。** 一个引用都没找到必须红：这个仓有过判据因为路径前缀
  写错而跳过全部 27 个文件、打出「0 个不同」差点被读成通过。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "dist" / "social-archive-extension.zip"

# 扫描集自检的下限。写成下限而不是精确值，是因为**精确值会逼着人为了过门
# 去删引用**；写成清单又会在产品正常演进时变成「守着一件不存在的事」。
MIN_FILES_SCANNED = 10
MIN_REFERENCES = 15


def _clean(path: str) -> str:
    """剥掉查询串和锚点。

    实测 `background.js` 里有 `runtime.getURL("options.html?onboarding=1")`
    和 `getURL("options.html#platforms")`——不剥的话会去找一个叫
    `options.html?onboarding=1` 的文件，报两个不存在的缺失。
    （第一版就是这么误报的。）
    """
    return path.split("?", 1)[0].split("#", 1)[0]


def _resolve(reference: str, referrer: str) -> str | None:
    """把一条引用解析成包内路径；不是包内文件就返回 None。"""
    if not reference:
        return None
    if reference.startswith(("http://", "https://", "data:", "chrome-extension://", "//")):
        return None
    if "*" in reference:
        return None
    reference = _clean(reference).strip()
    if not reference:
        return None
    if reference.startswith("/"):
        return reference.lstrip("/")
    base = referrer.rsplit("/", 1)[0] if "/" in referrer else ""
    # `./x` 和 `x` 都按引用者所在目录算；`../` 交给 posixpath 规范化
    import posixpath  # noqa: PLC0415
    joined = posixpath.normpath(posixpath.join(base, reference)) if base else posixpath.normpath(reference)
    return None if joined.startswith("..") else joined


def collect(members: dict[str, bytes]) -> dict[str, set[str]]:
    """返回 {包内路径: {谁引用了它, …}}。"""
    refs: dict[str, set[str]] = {}

    def note(reference: str, referrer: str, how: str) -> None:
        target = _resolve(reference, referrer)
        if target is not None:
            refs.setdefault(target, set()).add(f"{referrer}:{how}")

    for name, raw in sorted(members.items()):
        if not name.endswith((".js", ".html", ".json")):
            continue
        text = raw.decode("utf-8", errors="replace")

        if name == "manifest.json":
            manifest = json.loads(text)
            note((manifest.get("background") or {}).get("service_worker") or "",
                 "manifest.json", "background")
            for index, script in enumerate(m_cs := manifest.get("content_scripts") or []):
                for one in (script.get("js") or []):
                    note(one, "manifest.json", f"content_scripts[{index}].js")
                for one in (script.get("css") or []):
                    note(one, "manifest.json", f"content_scripts[{index}].css")
            del m_cs
            note((manifest.get("action") or {}).get("default_popup") or "", "manifest.json", "action")
            note((manifest.get("side_panel") or {}).get("default_path") or "", "manifest.json", "side_panel")
            note(manifest.get("options_page") or "", "manifest.json", "options_page")
            note((manifest.get("options_ui") or {}).get("page") or "", "manifest.json", "options_ui")
            for size, icon in (manifest.get("icons") or {}).items():
                note(icon, "manifest.json", f"icons[{size}]")
            for size, icon in ((manifest.get("action") or {}).get("default_icon") or {}).items():
                note(icon, "manifest.json", f"default_icon[{size}]")
            for index, war in enumerate(manifest.get("web_accessible_resources") or []):
                for one in (war.get("resources") or []):
                    note(one, "manifest.json", f"web_accessible_resources[{index}]")
            continue

        if name.endswith(".html"):
            for one in re.findall(r'<script[^>]*\ssrc=["\']([^"\']+)["\']', text, re.I):
                note(one, name, "script src")
            for one in re.findall(r'<link[^>]*\shref=["\']([^"\']+)["\']', text, re.I):
                note(one, name, "link href")
            continue

        # .js
        for group in re.findall(r'files\s*:\s*\[([^\]]*)\]', text):
            for one in re.findall(r'["\']([^"\']+\.(?:js|css))["\']', group):
                note(one, name, "executeScript")
        for one in re.findall(r'runtime\.getURL\(\s*["\']([^"\']+)["\']', text):
            note(one, name, "getURL")
        for group in re.findall(r'importScripts\(([^)]*)\)', text):
            for one in re.findall(r'["\']([^"\']+)["\']', group):
                note(one, name, "importScripts")
        for one in re.findall(r'(?:^|[\s;])import\s+(?:[^;\n]*?\sfrom\s+)?["\']([^"\']+)["\']', text):
            note(one, name, "import")

    return refs


# Cloudflare 按浏览器签名封 `Python-urllib`（error 1010，实测 403；curl 和不发 UA
# 都是 200）。仓里 `check_the_shipped_package_is_the_committed_code.py` 早就踩过并
# 定了这个写法——**照抄它，不另发明**：前缀让 Cloudflare 放行，括号里说真话表明
# 自己是什么，不冒充一个真浏览器。
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (package-check)"}


def read_members(source: str) -> dict[str, bytes]:
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers=BROWSER_UA)  # noqa: S310
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            raw = response.read()
        archive = zipfile.ZipFile(io.BytesIO(raw))
    else:
        archive = zipfile.ZipFile(source)
    with archive:
        return {info.filename: archive.read(info)
                for info in archive.infolist() if not info.is_dir()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default=str(DEFAULT_ZIP),
                        help="要检查的包；也可以给 http(s) 地址直接拉线上那份")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        members = read_members(args.zip)
    except Exception as error:  # noqa: BLE001
        print(f"✗ 读不到这个包：{args.zip}（{type(error).__name__}: {error}）")
        return 2

    refs = collect(members)
    present = set(members)
    missing = {path: sorted(who) for path, who in refs.items() if path not in present}

    scanned = sum(1 for n in present if n.endswith((".js", ".html", ".json")))
    verdict = {
        "zip": args.zip,
        "files_in_package": len(present),
        "files_scanned": scanned,
        "references_found": len(refs),
        "missing": missing,
    }

    # **空扫要当失败。** 引用一个都没找到、或者扫到的文件少得离谱，
    # 说明这道判据自己坏了（正则失效 / 包结构变了），不是「没问题」。
    if scanned < MIN_FILES_SCANNED or len(refs) < MIN_REFERENCES:
        verdict["status"] = "FAIL"
        verdict["why"] = (f"扫到 {scanned} 个文件、{len(refs)} 条引用，"
                          f"低于下限（{MIN_FILES_SCANNED} / {MIN_REFERENCES}）——"
                          "这是判据自己坏了，不是包没问题")
        print(json.dumps(verdict, ensure_ascii=False, indent=2) if args.json else "✗ " + verdict["why"])
        return 1

    # 运行时注入那一档必须还在被扫到。它整档消失 = 注入机制换了，要人看一眼，
    # 不能悄悄变成「没有这类引用所以全绿」。
    if not any("executeScript" in who for whos in refs.values() for who in whos):
        verdict["status"] = "FAIL"
        verdict["why"] = ("包里一条 executeScript 注入都没扫到——"
                          "要么注入机制换了、要么这道判据的正则失效了，两种都要人看一眼")
        print(json.dumps(verdict, ensure_ascii=False, indent=2) if args.json else "✗ " + verdict["why"])
        return 1

    if missing:
        verdict["status"] = "FAIL"
        if args.json:
            print(json.dumps(verdict, ensure_ascii=False, indent=2))
        else:
            print(f"✗ 包里缺 {len(missing)} 个它运行时会去取的文件：")
            for path, who in sorted(missing.items()):
                print(f"    {path}   ← 被 {', '.join(who)} 引用")
            print("  这些不会在装载时报错——只会在他点下去的那一刻静静失败。")
        return 1

    verdict["status"] = "PASS"
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    else:
        print(f"✓ 包里 {len(present)} 个文件；{len(refs)} 条运行时引用全部指得到实体"
              f"（扫了 {scanned} 个 js/html/json）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
