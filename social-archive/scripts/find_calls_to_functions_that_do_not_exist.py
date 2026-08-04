#!/usr/bin/env python3
"""界面脚本里调用了一个根本不存在的函数（v0.0.0.7）。

## 第六种「建好了没接上」

前五种：Python 符号没人引用、HTTP 接口没有界面调用、storage 键写了没人读、
扩展消息只有一头、配置项设不上。这一种更直接——**函数压根不存在**。

    await loadAccounts();     // 文件里只有 loadAccountsAndDestinations
    renderSyncModal();        // 文件里只有 renderSyncTable

`node --check` 照样通过：它只查语法，不查标识符。判据也测不到，
因为没人在 Node 里真的跑这个 IIFE。**只有用户点到那颗按钮的一刻才会炸**，
炸出来的是一句 ReferenceError，而按钮上写着"正在断开…"。

本轮就是这么写错的：给 PWA 加断开按钮时照着扩展那份的写法抄了刷新调用，
而两边的函数不同名。发现纯属偶然——顺手 grep 了一下那两个名字。

## 判据

每个界面脚本都是一个自包含的 IIFE。**在文件里被当成函数调用（`名字(`）
的名字，必须在同一个文件里声明过**，或者是浏览器/运行时全局。
属性调用（`x.y()`）不看——那是运行时对象的事。

先剥注释：本轮已经被自己写的说明文字骗过三次。

## 判据自己第一版造了 20 条误报

先只在六个 IIFE 文件上试跑，噪声极低（只有 `async`/`not`/`var`/`translateY`
这些关键字与 CSS 函数碎片）。**扩到全 apps/ 之后炸出 23 条**，其中 20 条来自
`obsidian-plugin/main.js` —— 那是个 class 写法的文件，而且它的运行时名字是
`const { Plugin, Notice } = require("obsidian")` 解构出来的。

也就是说：声明的形态不止 `function f`。补上 `class X`、类方法 `name(){}`、
以及解构声明之后归零。**"在小样本上噪声低"不等于"判据对"**——
本轮第五次因为射程/样本不足而先得出一个错结论。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"

DECLARED = re.compile(r'(?:function\s+|const\s+|let\s+|var\s+|class\s+)([A-Za-z_$][\w$]*)\s*(?:\(|=|\{|extends)')
# 解构声明：`const { Plugin, Notice } = require("obsidian")`。
# **第一版漏了这一条**，于是把 Obsidian 插件里所有从 require 解构出来的名字
# 全报成"不存在"——判据自己造出 20 条误报。
DESTRUCTURED = re.compile(r'(?:const|let|var)\s*[{\[]([^}\]]*)[}\]]\s*=')
# 类方法：`  onload() {` / `  async writeMarkdown(a, b) {`。它们不是 function 声明。
METHOD = re.compile(r'^\s*(?:async\s+)?(?:static\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{', re.M)
CALLED = re.compile(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(')
PARAMS = re.compile(r'\(([^()]*)\)\s*(?:=>|\{)')
IDENT = re.compile(r'[A-Za-z_$][\w$]*')

# 关键字、CSS 函数、浏览器与扩展运行时的全局。都不是"我们写的函数"。
NOT_OURS = frozenset("""
if for while switch catch return typeof new delete void await yield function class async
not var translateY rgba rgb calc
Array Object String Number Boolean Math JSON Date RegExp Promise Set Map WeakMap Error
URL URLSearchParams Headers FormData Blob File FileReader AbortController
TextEncoder TextDecoder Intl Symbol BigInt Proxy Reflect Uint8Array
parseInt parseFloat isNaN isFinite encodeURIComponent decodeURIComponent encodeURI decodeURI
setTimeout clearTimeout setInterval clearInterval requestAnimationFrame queueMicrotask
fetch alert confirm prompt structuredClone atob btoa importScripts
crypto console document window navigator location history globalThis chrome super this
getComputedStyle require constructor
addEventListener removeEventListener dispatchEvent Event CustomEvent
IntersectionObserver MutationObserver
""".split())


def code_only(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//") and not line.lstrip().startswith("*")
    )


# shared.js 的导出表：`return { api, apiText, activeTab, … }`。
# 扩展各页面通过全局 SA 用它们。
SA_EXPORTS = re.compile(r"\n    (?:return \{|)([\w,\s]+)\n  \};")


def shared_exports(root: Path) -> set[str]:
    """shared.js 到底导出了哪些名字。

    **属性调用是前面那套检查的盲区**：`SA.detectPlatform(...)` 里
    detectPlatform 前面有个点，正则特意跳过了它。而本轮已经三次
    因为「引用了不存在的名字」在运行时才炸——两次是变量，一次就是
    这种 SA.xxx。SA 这个命名空间的导出表是可枚举的，那就枚举它。
    """
    path = root / "apps/browser-extension/shared.js"
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="ignore")
    # **导出表在 `globalThis.SA = Object.freeze({ … })` 里，不是 return 语句。**
    # 第一版按 `return {…}` 找，抓到的是别处几个无关的对象字面量，
    # 于是 26 个真实存在的 SA.* 全被报成「不存在」——**判据自己造出的假红**。
    match = re.search(r"globalThis\.SA\s*=\s*Object\.freeze\(\{(.*?)\}\)", text, re.S)
    if not match:
        return set()
    return {
        name.strip() for name in match.group(1).replace("\n", " ").split(",")
        if name.strip().isidentifier()
    }


def undefined_sa_calls(text: str, exports: set[str]) -> list[str]:
    """`SA.foo(` 里的 foo 必须在 shared.js 的导出表里。"""
    if not exports:
        return []
    used = set(re.findall(r"\bSA\.(\w+)\s*\(", text))
    return sorted(used - exports)


def undefined_calls(text: str) -> list[str]:
    code = code_only(text)
    declared = set(DECLARED.findall(code)) | set(METHOD.findall(code))
    for group in DESTRUCTURED.findall(code):
        declared |= set(IDENT.findall(group))
    for signature in PARAMS.findall(code):
        declared |= set(IDENT.findall(signature))
    return sorted(set(CALLED.findall(code)) - declared - NOT_OURS)


def main() -> int:
    if not APPS.is_dir():
        print("找不到 apps/，跳过（这是跳过，不是通过）")
        return 0

    broken: dict[str, list[str]] = {}
    scanned = 0
    exports = shared_exports(ROOT)
    for path in sorted(APPS.rglob("*.js")):
        if "node_modules" in str(path):
            continue
        scanned += 1
        source = path.read_text(encoding="utf-8", errors="ignore")
        missing = undefined_calls(source)
        missing += [f"SA.{name}" for name in undefined_sa_calls(code_only(source), exports)]
        if missing:
            broken[str(path.relative_to(ROOT))] = missing

    print(f"扫了 apps/ 下 {scanned} 个脚本")
    if not broken:
        print("每一处函数调用都找得到定义。")
        return 0

    total = sum(len(v) for v in broken.values())
    print(f"\n**调用了 {total} 个不存在的函数** —— node --check 查不出来，"
          "判据也测不到，只有用户点到那颗按钮的一刻才会炸：")
    for file, names in broken.items():
        print(f"  {file}")
        for name in names:
            print(f"        {name}()")
    print("\n改成真实存在的名字，或把确实是运行时全局的加进 NOT_OURS。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
