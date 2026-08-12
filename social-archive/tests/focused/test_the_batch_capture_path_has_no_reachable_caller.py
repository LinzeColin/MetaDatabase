"""「有调用点」不等于「走得到」——批量保存那条路今天没人走（v0.0.0.7 / T08）。

## 这条判据在钉什么

`captureActive` 里有两条分支：`mode === "list"` 走 `/v1/captures/batch`
批量保存，否则单条保存。2026-08-05 把四个调用方全数了一遍：

  · `popup.js:174`      mode: "page"
  · `content/fab.js:25` mode: "page"
  · `background.js:1343` 快捷键     mode: "page"
  · `background.js:1364` 右键菜单   mode: "page"

**没有任何一处传 list。** 于是那条分支、连同 `/v1/captures/batch` 这个端点，
今天走不到；`savedCount` / `failedCount` 也没有任何界面读。

## 为什么这不是缺陷，但必须记下来

界面没有骗人：popup 里明写着「小红书、抖音、B站、快手的收藏列表现在还读不了」。
批量那条路是**先建好、等 T10 把取数通路接上**——这种「建在前面」本身没问题。

有问题的是**它把一道门骗过去了**：`find_endpoints_no_client_calls.py` 判断
「这个端点有没有客户端在调」，靠的是在客户端代码里找到那个路径字符串——
而 `background.js:116` 确实写着 `/v1/captures/batch`。
**门是绿的，指着一段永远不会执行的代码。**（这一天里同类的事已经第九次了。）

## 它红的时候该做什么

有人把 list 模式接上界面时这条会红——**那正是要的**：
红了就去把上面那道门的认知、以及 T10 的记录一起更新，别让「建在前面」
的状态无声无息地变成「已经在跑」而没人重新想过。
"""

from __future__ import annotations

import re
from pathlib import Path

EXT = Path(__file__).resolve().parents[2] / "apps/browser-extension"


def _senders() -> list[tuple[str, str]]:
    """把每个 `mode: "..."` 的取值连同出处收集起来。"""
    found: list[tuple[str, str]] = []
    for path in sorted(EXT.rglob("*.js")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            for match in re.finditer(r'\bmode:\s*"(\w+)"', line):
                found.append((f"{path.relative_to(EXT)}:{line_no}", match.group(1)))
    return found


def test_no_caller_asks_for_list_mode_today() -> None:
    """**四个调用方全是 page。** 变了就该重新想一遍，而不是悄悄生效。"""
    senders = _senders()
    assert senders, "一个 mode: 都没找到——判据的射程写错了，先修判据"
    asking_for_list = [where for where, mode in senders if mode == "list"]
    assert not asking_for_list, (
        "**有人把批量保存接上了**：" + ", ".join(asking_for_list) + "。\n"
        "这条判据红了不是坏事，是提醒：\n"
        "  · `find_endpoints_no_client_calls.py` 对 /v1/captures/batch 的认知要更新"
        "（它此前是靠一段走不到的代码过关的）；\n"
        "  · savedCount / failedCount 此前没有任何界面读，接上之后"
        "**部分失败必须让用户看见**——现在的文案只说「当前页面已保存」。"
    )


def test_the_batch_branch_still_exists_so_the_note_is_about_something_real() -> None:
    """反过来也要钉住：分支还在。

    **少了这条，把整条批量分支删掉，上面那条照样绿**——
    而那时这份记录说的就是一件不存在的事。
    """
    background = (EXT / "background.js").read_text(encoding="utf-8")
    assert 'message.mode === "list"' in background, "批量分支不见了——这份记录要跟着删"
    assert "/v1/captures/batch" in background, "批量端点的调用点不见了"
