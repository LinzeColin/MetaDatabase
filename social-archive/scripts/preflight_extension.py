#!/usr/bin/env python3
"""扩展装载前自检（v0.0.0.7）。

## 为什么需要它

T02 / T04 / T06 / T08 的验收都卡在同一件事上：Owner 把扩展以未打包形式载入
Chrome。那一步只有 Owner 能做，我做不了。**我能做的是保证他做那一步时不白做。**

Chrome 加载未打包扩展时，manifest 里引用了不存在的文件、或者哪个脚本有语法错，
会直接报错拒绝加载——而报错信息经常只说"Could not load javascript ..."，
不告诉你是哪一处引用断了。让 Owner 去猜是浪费他的时间。

这个脚本把那些会导致加载失败的情况提前查出来：

  1. manifest.json 本身合法
  2. manifest 引用的每个文件都真的存在（background / content_scripts /
     web_accessible_resources / 各个 html 页面 / icons）
  3. 每个 .js 都能通过 `node --check`
  4. background.js 的 importScripts 目标都存在
  5. 每个 .html 里 <script src> 引用的文件都存在
  6. 代码里调用的 chrome API 与 manifest 声明的权限对得上
     （少声明会在运行时才炸，那时已经装上了、更难查）

## 退出码

0 = 可以装；1 = 有会导致加载失败或运行时炸掉的问题；2 = 自检本身出错。

**扫到 0 个文件也算失败**，报 2 而不是 0。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "apps" / "browser-extension"

# chrome API → 需要的 manifest 权限。只列会因缺权限而在运行时抛错的那些。
# 可选权限（optional_permissions）也算声明过——它们在运行时 request。
API_PERMISSIONS = {
    "chrome.bookmarks": "bookmarks",
    "chrome.cookies": "cookies",
    "chrome.contextMenus": "contextMenus",
    "chrome.scripting": "scripting",
    "chrome.storage": "storage",
    "chrome.alarms": "alarms",
    "chrome.sidePanel": "sidePanel",
}


def problems() -> list[str]:
    found: list[str] = []
    manifest_path = EXT / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json 不存在"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"manifest.json 不是合法 JSON：{exc}"]

    # ── manifest 引用的文件 ──
    referenced: list[str] = []
    background = manifest.get("background", {})
    if background.get("service_worker"):
        referenced.append(background["service_worker"])
    for entry in manifest.get("content_scripts", []):
        referenced += entry.get("js", []) + entry.get("css", [])
    for key in ("options_page",):
        if manifest.get(key):
            referenced.append(manifest[key])
    if manifest.get("side_panel", {}).get("default_path"):
        referenced.append(manifest["side_panel"]["default_path"])
    if manifest.get("action", {}).get("default_popup"):
        referenced.append(manifest["action"]["default_popup"])
    for entry in manifest.get("web_accessible_resources", []):
        referenced += entry.get("resources", [])
    for icon in (manifest.get("icons") or {}).values():
        referenced.append(icon)

    for relative in referenced:
        if not (EXT / relative).is_file():
            found.append(f"manifest 引用了不存在的文件：{relative}")

    # ── 语法 ──
    js_files = sorted(EXT.rglob("*.js"))
    if not js_files:
        found.append("一个 .js 都没扫到——自检在空转")
    for path in js_files:
        completed = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True, check=False
        )
        if completed.returncode:
            found.append(f"{path.relative_to(EXT)} 语法错误：{completed.stderr.strip()[:200]}")

    # ── importScripts 目标 ──
    worker = EXT / background.get("service_worker", "background.js")
    if worker.is_file():
        text = worker.read_text(encoding="utf-8")
        for match in re.finditer(r"importScripts\(([^)]*)\)", text):
            for target in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
                if not (EXT / target).is_file():
                    found.append(f"background.js importScripts 了不存在的文件：{target}")

    # ── html 里的 script src ──
    for html in sorted(EXT.rglob("*.html")):
        text = html.read_text(encoding="utf-8")
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text):
            if src.startswith(("http://", "https://", "//")):
                found.append(f"{html.name} 引用了外部脚本 {src}——MV3 的 CSP 会拒绝")
                continue
            target = (html.parent / src).resolve()
            if not target.is_file():
                found.append(f"{html.name} 引用了不存在的脚本：{src}")

    # ── 权限与调用对不对得上 ──
    declared = set(manifest.get("permissions", [])) | set(manifest.get("optional_permissions", []))
    all_js = "\n".join(
        "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith(("//", "*", "/*"))
        )
        for path in js_files
    )
    for api, permission in API_PERMISSIONS.items():
        if api in all_js and permission not in declared:
            found.append(f"代码调用了 {api} 但 manifest 没声明 {permission} 权限——运行时才会炸")

    # ── 已删文件的残留引用 ──
    for gone in ("account-mirror-core.js", "account-mirror.js"):
        if gone in all_js:
            found.append(f"代码里还引用着已删除的 {gone}")

    return found


def main() -> int:
    try:
        found = problems()
    except Exception as exc:  # noqa: BLE001
        print(f"!! 自检本身出错：{exc}", file=sys.stderr)
        return 2
    if found:
        print(f"!! 扩展现在装不上或装上会炸，共 {len(found)} 处：", file=sys.stderr)
        for item in found:
            print(f"   · {item}", file=sys.stderr)
        return 1
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    js_count = len(list(EXT.rglob("*.js")))
    print(f"可以装载。manifest v{manifest.get('manifest_version')}、"
          f"version {manifest.get('version')}、{js_count} 个脚本全部通过检查。")
    print(f"路径：{EXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
