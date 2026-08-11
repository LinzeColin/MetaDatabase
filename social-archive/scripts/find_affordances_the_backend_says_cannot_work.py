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

## 第四处：连接器状态视图（2026-08-05 补）

前面守的是两个**界面**。2026-08-05 又在第三个地方发现同一种假话——
服务端自己产出的连接器健康视图：

    instagram  healthy  「可直接点击"读取/保存"。」
    bilibili   healthy  「可直接点击"读取/保存"。」
    tiktok     healthy  「可直接点击"读取/保存"。」

而真跑一次全都是 blocked。根因：那三个的探针是 `command.health()`，
它测的是**「CLI sidecar 活着吗」**，不是「这个连接器干得成活吗」。

所以这道门多守一处：`registry.health_views` 必须拿 SYNCABLE_NOW /
NOT_SYNCABLE_YET 钳一次，**不得比产品自己的能力声明更乐观**。

## 它不保证什么

- 只查「有没有看那个字段」，不查「看得对不对」。
- 只覆盖平台级承诺（同步按钮、连接入口、连接器健康度）。
  别的按钮（导出、分类…）不在射程里。
- **这道门是事后补的。** 四处假话没有一处是它发现的，
  全是 Owner 撞出来的，或者我给别的事取证时顺手撞见的。
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
        "guards": (
            # **钉住完整表达式，一条渲染路径一条。**（2026-08-11）
            #
            # 原来写的是子串 `sync_supported === false`，而它在这个函数里出现
            # **两次**（第 9 行「这个平台没有账号」那条路、第 43 行账号行那条路）。
            # 于是把第 43 行那个守卫改成常量 `false`，这道门照样是绿的——
            # 文件头里写着的那次假通过，用同一个机制又发生了一遍。
            # 抓到它的是「逐条真去改坏」，不是读代码。
            "support?.sync_supported === false",
            "state.platformSupport[account.platform]?.sync_supported === false",
            # **第二个前提：账号得连着。**（2026-08-11）
            #
            # 这道门原来只守「这个平台现在同步得动吗」（能力），
            # 漏了「这个账号现在连着吗」（状态）。两个前提都不满足就点不动，
            # 而它只查了一个——于是 Owner 三个 disconnected 账号那几行上
            # 各摆着一颗「立即同步」。真镜像上实测：
            #     已连接  POST /v1/accounts/{id}/sync → 202
            #     已断开  同一条 → 422「账号尚未连接，请先完成授权」
            'account.connection_state === "disconnected"',
        ),
        # **每条守卫管哪几颗按钮**（2026-08-11 补）。
        # 原来一律要求「所有守卫都排在所有按钮之前」，而
        # `connection_state === "disconnected"` 那一支画出来的正是
        # `data-connect-platform`（「连接账号」）——它是**补救**，不是假承诺。
        # 一刀切会把正确的写法判红。所以按标记分开。
        "guard_scope": {
            "support?.sync_supported === false": (
                "data-sync-account", "data-connect-platform"),
            "state.platformSupport[account.platform]?.sync_supported === false": (
                "data-sync-account",),
            'account.connection_state === "disconnected"': ("data-sync-account",),
        },
    },
    {
        "file": "apps/browser-extension/options.js",
        "function": "renderAccounts",
        # 扩展那侧先算成一个变量，再用它分支——两处都得在
        "guards": (
            "platformSupport[platform]?.sync_supported !== false",
            "!syncable",
            # **同一个第二前提。** 这个文件头自己写着「两个界面各有一份，
            # 第一轮只修了网页那侧」——2026-08-11 我又原样犯了一次：
            # PWA 那侧修完就以为完了，扩展设置页这一支只问「有没有 account」，
            # 从不问它连着没有。
            'account.connection_state === "disconnected"',
        ),
        "guard_scope": {
            "platformSupport[platform]?.sync_supported !== false": (
                "data-sync-account", "data-connect-platform"),
            "!syncable": ("data-sync-account", "data-connect-platform"),
            'account.connection_state === "disconnected"': ("data-sync-account",),
        },
    },
)
# 承诺「点了会同步/会连上」的按钮标记。
PROMISING_MARKERS = ("data-sync-account", "data-connect-platform")
CAPABILITY = "sync_supported"

# 服务端自己产出的、会被当成「这个平台能用」的视图。
# 它不是界面文件，所以上面那套 SURFACES 查不到它。
SERVER_SIDE_SURFACES = (
    {
        "file": "src/social_archive/registry.py",
        "function": "health_views",
        "guards": ("connector_id in NOT_SYNCABLE_YET", "connector_id not in SYNCABLE_NOW"),
        "why": "连接器健康度不得比 SYNCABLE_NOW / NOT_SYNCABLE_YET 更乐观",
    },
)


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
        # 顺序也要对：守卫必须在**它管的那颗按钮**之前，否则按钮已经画出去了。
        #
        # 按标记分别算，不再一刀切——`connection_state === "disconnected"`
        # 那一支画的就是「连接账号」，把它算成"假承诺"会把正确写法判红。
        scope = surface.get("guard_scope") or {g: PROMISING_MARKERS for g in guards}
        for marker in used:
            relevant = [g for g in guards if marker in scope.get(g, PROMISING_MARKERS)]
            if not relevant:
                continue
            guard_at = max(block.index(g) for g in relevant)
            if block.index(marker) < guard_at:
                problems.append(
                    f"  {rel} 的 {function}()：{marker} 出现在守卫"
                    f"{[g for g in relevant if block.index(g) > block.index(marker)]}之前——"
                    "那颗按钮还是会被画出来"
                )

    for surface in SERVER_SIDE_SURFACES:
        rel, function, guards = surface["file"], surface["function"], surface["guards"]
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"  {rel}：文件不存在——判据失去依附，别当成通过")
            continue
        code = code_only(path.read_text(encoding="utf-8", errors="ignore"))
        if f"def {function}" not in code:
            problems.append(f"  {rel}：找不到 {function}()——改名了，判据要跟着改")
            continue
        block = code.split(f"def {function}", 1)[1]
        nxt = re.search(r"\n    def ", block)
        if nxt:
            block = block[: nxt.start()]
        checked += 1
        missing = [g for g in guards if g not in block]
        if missing:
            problems.append(
                f"  {rel} 的 {function}()：这些守卫不在了：{missing}"
                f" —— {surface['why']}"
            )

    print(f"检查了 {checked} 处会承诺「这个平台能用」的地方（界面 + 服务端视图）")
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
