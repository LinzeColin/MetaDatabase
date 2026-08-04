#!/usr/bin/env python3
"""界面画了一颗按钮，而服务端已经说过那件事做不到（v0.0.0.7）。

## 第七种「建好了没接上」，也是最贵的一种

前六种都是**代码之间**没接上（符号没人引用、接口没人调、消息只有一头……）。
这一种不同：代码全都接上了，**它对用户说了做不到的事**。

Owner 用完之后的原话：

    「非常不好用 而且你的流程逻辑非常混乱 我都不知道应该怎么操作」
    「点击同步不就是自动刷新全部同步吗，怎么实际功能和显示文字还不一样」

当时十八道门全绿、614 条判据全过。它们证明的是「函数写得对」「接口有人调」
「文案能落到一句中文」——**没有一条在问「这颗按钮点下去会发生它承诺的事吗」**。

实际发生的：小红书 / 抖音 / B站 三张卡片都画着「立即同步」，
点下去走到一个显式 stub，而那个失败码被别名成「暂时连不上服务器，[ 重试 ]」。
**用户一遍遍重试一件结构上不可能成功的事。**

## 判据

服务端在 `account_sync.SYNCABLE_NOW` 里声明了「现在真的同步得动的平台」，
并经 `/v1/accounts` 的 `supported_platforms[].sync_supported` 下发。

**凡是渲染平台级动作按钮的地方，都必须先看这个字段。**

被检查的按钮标记：
  · `data-sync-account`     立即同步
  · `data-connect-platform` 连接账号 / 重新连接

被检查的文件：`apps/pwa/app.js` 与 `apps/browser-extension/options.js`
——**两个界面各有一份**。第一轮只修了网页那侧，扩展设置页原样留着
同样的三处假话；这道门就是为了不再漏掉另一半。

## 它不保证什么

- 只查「有没有看那个字段」，不查「看得对不对」。
- 只覆盖平台级同步这一类承诺。别的按钮（导出、分类…）不在射程里。
- **这道门是事后补的。** 三处假话没有一处是它发现的，全是 Owner 撞出来的。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 渲染平台级动作的界面。每一项写清**真正起作用的那个守卫表达式**，
# 而不只是「有没有提到 sync_supported」。
#
# 第一版就是只查「函数体里有没有出现 sync_supported」——**给了一次假通过**：
# 反证把守卫的值改成常量 true，而那个字符串在同一函数的别处（渲染说明文字那段）
# 还在，门照样放行。**判据被同一函数里另一处无关的引用满足了。**
#
# 现在钉住守卫本身。有人重构改了写法，这道门会说「判据失去依附，请重写」
# 而不是安静放行——**大声失效比安静通过好**。
SURFACES = (
    {
        "file": "apps/pwa/app.js",
        "function": "renderSyncTable",
        # 网页那侧直接在分支条件里判
        "guards": ("sync_supported === false",),
    },
    {
        "file": "apps/browser-extension/options.js",
        "function": "renderAccounts",
        # 扩展那侧先算成一个变量，再用它分支——两处都得在
        "guards": (
            "platformSupport[platform]?.sync_supported !== false",
            "!syncable",
        ),
    },
)
# 承诺「点了会同步/会连上」的按钮标记。
PROMISING_MARKERS = ("data-sync-account", "data-connect-platform")
CAPABILITY = "sync_supported"


def code_only(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//") and not line.lstrip().startswith("*")
    )


def main() -> int:
    problems: list[str] = []
    checked = 0

    for surface in SURFACES:
        rel, function, guards = surface["file"], surface["function"], surface["guards"]
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"  {rel}：文件不存在——判据失去依附，别当成通过")
            continue
        code = code_only(path.read_text(encoding="utf-8", errors="ignore"))
        if f"function {function}" not in code:
            problems.append(f"  {rel}：找不到 {function}()——渲染入口改名了，判据要跟着改")
            continue
        block = code.split(f"function {function}", 1)[1]
        # 截到下一个顶层函数定义为止
        nxt = re.search(r"\n  (?:async )?function ", block)
        if nxt:
            block = block[: nxt.start()]
        checked += 1

        used = [m for m in PROMISING_MARKERS if m in block]
        if not used:
            continue  # 这一屏没画承诺型按钮

        missing = [g for g in guards if g not in block]
        if missing:
            problems.append(
                f"  {rel} 的 {function}() 画了 {', '.join(used)}，"
                f"而这些守卫不在了：{missing}"
                " —— 要么服务端说做不到的事界面照样给按钮，要么写法变了、判据要跟着重写"
            )
            continue
        # 顺序也要对：守卫必须在按钮之前，否则按钮已经画出去了
        guard_at = max(block.index(g) for g in guards)
        for marker in used:
            if block.index(marker) < guard_at:
                problems.append(
                    f"  {rel} 的 {function}()：{marker} 出现在守卫之前——"
                    "那颗按钮还是会被画出来"
                )

    print(f"检查了 {checked} 个渲染平台级动作的界面")
    if problems:
        print(f"\n**{len(problems)} 处界面在承诺服务端说做不到的事**：")
        for line in problems:
            print(line)
        print(f"\n先看 {CAPABILITY} 再决定画不画按钮；"
              "做不到就把「为什么」和「现在能做什么」写在那个位置上。")
        return 1
    print("每一处承诺型按钮都先问过服务端能不能做到。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
