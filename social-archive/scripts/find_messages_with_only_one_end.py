#!/usr/bin/env python3
"""扩展消息只有一头：有人听没人发，或有人发没人听（v0.0.0.7）。

## 为什么再加一道

前三道门看的是三种「建好了没接上」：

    find_unwired_code.py               Python 符号没人引用
    find_endpoints_no_client_calls.py  HTTP 接口没有界面调用
    find_write_only_storage_keys.py    storage 键写了没人读

**扩展内部靠消息互通的那一层，三道门一道都看不见。** 它的两种坏法：

1. **有人听、没人发**——处理体写得完整、测试也测得过，而全仓没有任何地方
   发出这条消息。功能在代码上是完整的，在产品上不存在。
2. **有人发、没人听**——消息发出去落到虚空。MV3 里 `sendMessage` 没有接收方
   会 reject，而发送处通常 `.catch(() => {})`，于是连报错都看不见。

## 本轮实际抓到的（这道门是这么来的）

    SA_REVOKE_PLATFORM_SESSION   有人听、没人发
    SA_NET_OBSERVER_STATE        有人发、没人听

第一条尤其要紧：连接成功时产品**当着用户面许诺**「随时可以一键撤销」，
而撤销这件事只存在于两处代码里（服务端 DELETE 路由 + 扩展处理体），
没有任何界面能发出那条消息。**那句承诺在产品上是假的。**

第二条是观察器自报「我装好了」，而 background 没有对应处理体——
安装那段注释里明写「丢掉 INSTALLED 的后果是 background 分不清
『装好了』和『注入静默失败了』」，然后就丢了。

## 判据

扫 `apps/` 下的 `.js`/`.html`，取所有 `"SA_XXX"` 字面量：

  · **消费**：`x.type === "SA_XXX"` / `case "SA_XXX"`
  · **生产**：除消费之外的任何一次出现（`sendMessage({type:…})`、
    `postToExtension("SA_XXX", …)`、`post("SA_XXX", …)` 都算）

宽松地认生产、严格地认消费——宁可漏报也不误报。注释先剥掉：
本轮已经被自己写的说明文字骗过三次（注释里提到一个名字被当成了引用）。

## 应答消息按 requestId 对上，不按 type

第一版把 `SA_PONG` 和六条 `SA_*_RESULT` 全报成「有人发、没人听」。**是误报。**
去读消费方才发现：页面侧的 `postToExtension()` 用 `crypto.randomUUID()` 生成
requestId，回来时只比对 `data.requestId === requestId`，**根本不看 type**。

所以判据加一条：某个名字的所有生产处都带着 requestId，它就是一条有主的应答，
不是掉进虚空的消息。这不是给它开后门，是按它真实的对应机制判定。

## 只看 apps/

判据脚本里发一条消息**不算**产品里有人发。验收脚本能驱动的东西，
用户点不到。这条区别正是本轮反复吃亏的地方。

## 豁免

写进 ONE_ENDED_ON_PURPOSE，每条必须说清两件事：为什么现在只有一头，
以及**什么条件下它会被接上**。写不出第二条的，就不是豁免，是该删。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"

MESSAGE = re.compile(r'"(SA_[A-Z0-9_]+)"')


def consumer_patterns(name: str) -> list[re.Pattern[str]]:
    quoted = re.escape(f'"{name}"')
    return [
        re.compile(rf"\.type\s*===?\s*{quoted}"),
        re.compile(rf"{quoted}\s*===?\s*\w+(?:\?)?\.type"),
        re.compile(rf"\.type\s*!==?\s*{quoted}"),
        re.compile(rf"case\s+{quoted}"),
    ]


# 只有一头、但**现在**是对的。每条都要写清楚什么时候会被接上。
ONE_ENDED_ON_PURPOSE: dict[str, str] = {
    # **本来这里有两条：SA_INSTALL_NET_OBSERVER 与 SA_GET_NET_CAPTURES。**
    # 它们现在真的有发送方了——popup 的「帮开发者看一眼这个平台」按钮，
    # 所以从名单里去掉。豁免用完就该退掉，留着会变成一张没人再核的名单。
}


def strip_comments(text: str) -> str:
    """剥掉行注释与块注释行。名字出现在注释里不算引用。"""
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        out.append(line.split("//")[0] if "//" in line and '"' not in line.split("//")[0][-2:] else line)
    return "\n".join(out)


def main() -> int:
    if not APPS.is_dir():
        print("找不到 apps/，跳过（这是跳过，不是通过）")
        return 0

    sources = {
        path: strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        for path in sorted(APPS.rglob("*"))
        if path.is_file() and path.suffix in {".js", ".html"} and "node_modules" not in str(path)
    }
    blob = "\n".join(sources.values())
    names = sorted(set(MESSAGE.findall(blob)))

    listen_only: list[str] = []
    send_only: list[str] = []
    for name in names:
        consumers = 0
        producers = 0
        correlated = 0
        for text in sources.values():
            for line in text.splitlines():
                if f'"{name}"' not in line:
                    continue
                hits = len(re.findall(re.escape(f'"{name}"'), line))
                matched = sum(
                    len(pattern.findall(line)) for pattern in consumer_patterns(name)
                )
                consumers += matched
                produced_here = max(0, hits - matched)
                producers += produced_here
                if produced_here and "requestId" in line:
                    correlated += produced_here
        # 全部生产处都带 requestId = 这是一条应答，页面按 requestId 收，不看 type。
        if producers and correlated == producers:
            continue
        if consumers and not producers and name not in ONE_ENDED_ON_PURPOSE:
            listen_only.append(name)
        if producers and not consumers and name not in ONE_ENDED_ON_PURPOSE:
            send_only.append(name)

    print(f"扫了 apps/ 下 {len(sources)} 个文件，{len(names)} 个 SA_ 消息类型；"
          f"另有 {len(ONE_ENDED_ON_PURPOSE)} 条已登记的单头例外")
    if not listen_only and not send_only:
        print("每条消息都既有发送方也有接收方。")
        return 0

    if listen_only:
        print(f"\n**有人听、没人发的 {len(listen_only)} 条** —— "
              "处理体在代码上是完整的，在产品上够不着：")
        for name in listen_only:
            print(f"  {name}")
    if send_only:
        print(f"\n**有人发、没人听的 {len(send_only)} 条** —— "
              "消息落进虚空，发送处通常 catch 掉，连报错都看不见：")
        for name in send_only:
            print(f"  {name}")
    print("\n接上另一头，或删掉这一头；确实该单头存在的，"
          "写进 ONE_ENDED_ON_PURPOSE 并说清什么条件下会被接上。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
