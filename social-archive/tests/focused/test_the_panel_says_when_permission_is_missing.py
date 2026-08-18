r"""连接面板必须当场说出「缺授权」，不能等一次同步失败（2026-08-18）。

## 它修的是什么

2026-08-17 生产实况：他三个账号都显示**已连接**，而每次同步倒在
`PLATFORM_PERMISSION_MISSING` —— 浏览器那颗「允许读取该平台页面」的授权
根本没给到。真 Chrome 探针同时证实 `permissions.contains({origins:抖音}) = false`。

**「已连接」和「读得到」是两件事，而界面上只显示前一件。** 他没有任何办法
提前发现，只能等一次同步失败后才看到那句话；而同步那一刻没有用户手势，
`chrome.permissions.request` 一定抛，所以那时也补不回来。

## 为什么要有这道判据

`connect-frame.js` 里**建行的代码有两处**（可同步的一处、connect_supported 的一处）。
我第一版只改了后面那处 —— 于是 X / YouTube 标出来了，而
**小红书 / 抖音 / B站（他真正在用的三个）一行都没标**，真 Chrome 里一眼看见。
「两处只改了一处」这个仓当天已经第二次。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "apps/browser-extension/connect-frame.js"


def _code() -> str:
    """剥掉注释再看 —— 说明里写着函数名不等于代码调了它。"""
    text = PANEL.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("//"))


def test_每一处画了连接按钮的地方都要标授权() -> None:
    """**配对关系，不是阈值。**

    第一版我写的是「markPermission 次数 ≥ list.append 次数 - 1」——
    拿反例一跑（删掉其中一处调用）**它没红**：阈值刚好还成立。
    判据守错了口径，和它纪念的那个缺陷是同一种错。

    真正的不变量是：**画得出「连接账号」按钮的每一处，都得标授权**——
    因为「能点连接」正好等价于「这个平台需要浏览器授权」。
    """
    code = _code()
    buttons = len(re.findall(r"connectButtonFor\(", code)) - 1   # 减去它自己的定义
    marks = len(re.findall(r"markPermission\(", code)) - 1       # 同理
    assert buttons >= 2, f"画按钮的地方只找到 {buttons} 处，这道判据的前提变了"
    assert marks == buttons, (
        f"画「连接账号」按钮的有 {buttons} 处，而标授权的只有 {marks} 处——"
        "少的那一处，那批平台永远不会被标出「缺授权」。\n"
        "  2026-08-18 实测：漏掉的那处正好是小红书/抖音/B站，他真正在用的三个。")


def test_这个标记只读_不许弹框() -> None:
    """**面板渲染时不许申请权限。**

    `chrome.permissions.request` 要用户手势；在 render 里调它一定抛，
    而且就算不抛，一打开面板就弹七个授权框也是不能接受的。
    这里只允许 `contains`。
    """
    code = _code()
    body = re.search(r"async function markPermission\((.*?)\n  \}", code, re.S)
    assert body, "找不到 markPermission —— 改名了就把这条一起改"
    assert "permissions.contains" in body.group(1), "标记必须用 contains 查"
    assert "permissions.request" not in body.group(1), (
        "markPermission 里出现了 request —— 渲染时申请权限会抛，"
        "而且会一次弹一串框")


def test_查不动时不许显示成没有授权() -> None:
    """`contains` 抛了要**什么都不改**，不能把「我没查到」显示成「没有授权」。"""
    code = _code()
    body = re.search(r"async function markPermission\((.*?)\n  \}", code, re.S).group(1)
    assert re.search(r"catch\s*\([^)]*\)\s*\{\s*return", body), (
        "markPermission 的 catch 里没有直接 return —— "
        "查不动时会往下走到「缺授权」，那是把不知道说成了知道")
