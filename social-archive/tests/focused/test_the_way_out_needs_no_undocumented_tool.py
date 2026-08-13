r"""脚本给的出路，必须是接手方真的走得通的那条（2026-08-14）。

## 它修的是什么

`HANDOFF.md` 的可粘提示词告诉接手方：**改代码之后必须跑
`bash scripts/deploy_to_production.sh`**。新克隆的仓里没有 `.venv`，
所以他第一次跑就会撞上那道自检——这一步做对了，**不是静默失败，会给他一条命令**。

问题是那条命令原来写的是：

    uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -e '.[test]'

而 **`uv` 在整个仓里只出现在这一处**：任何 `.md` 都没说它是前置条件。
接手方（或接手的 AI）照做 → `command not found: uv` → 他得先去查 uv 是什么、
从哪装、装了会不会影响别的。**一个本来两分钟的坎变成一次外部依赖决策。**

而这个仓自己的安装脚本 `scripts/install.sh` 建 venv 用的是**标准库**：

    "$PYTHON" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/pip install -e '.[test]'

**出路已经存在，而错误提示指向了另一条更难、且没文档的。**
（同族：错误提示指向一个不存在的出口；工具已存在我却手工做。）

顺带：这条也服务于 Owner 说的「0 claude 依赖」——
一个只在错误提示里出现的第三方工具，同样是依赖。

## 口径

只管**部署脚本印给人看的补救命令**。别的脚本另有判据；
这里不试图证明"全仓零第三方"，那是另一件事，写出来免得被当成覆盖了全部。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts/deploy_to_production.sh"


def _venv_message() -> str:
    """venv 不在时那一段 `fail "..."` 的正文。"""
    text = DEPLOY.read_text(encoding="utf-8")
    match = re.search(r'fail "本地 venv 不在(.*?)"\n', text, flags=re.S)
    assert match, (
        "部署脚本里找不到「本地 venv 不在」那段提示。\n"
        "  它改名了就把这里一起改——否则这道判据会对着空字符串永远绿。")
    return match.group(1)


def test_重建venv的出路只用标准库() -> None:
    """**必须有一条不装任何东西就能走的路。**"""
    message = _venv_message()
    assert "-m venv" in message, (
        "重建 venv 的提示里没有 `-m venv`（标准库那条路）：\n" + message)
    assert "pip install" in message, (
        "只建了 venv 没装依赖，跑到下一步还是会炸：\n" + message)


def test_提到uv就必须说清它不是前置条件() -> None:
    """`uv` 可以留着（它确实更快），但**不许让人以为非它不可**。"""
    message = _venv_message()
    if "uv " not in message:
        return
    assert "不是前置条件" in message, (
        "提示里出现了 uv，却没说清它不是必须的。\n"
        "  `uv` 在整个仓里只出现在部署脚本里，任何 .md 都没写它是前置依赖——\n"
        "  接手方照做会得到 command not found，然后卡在一次外部依赖决策上。\n"
        + message)


def test_标准库那条要排在uv前面() -> None:
    """**人只会照着第一条做。** 把可选的快捷路子放前面，等于没给退路。"""
    message = _venv_message()
    # **先让位给上面那条。** 不加这个守卫的话，`-m venv` 整个不存在时
    # 这里会以 ValueError 崩掉——同一件事报两次、而且第二次报得看不懂。
    # （反例实测：预测 2 红实得 3 红，差额就是这个。）
    if "uv " not in message or "-m venv" not in message:
        return
    assert message.index("-m venv") < message.index("uv "), (
        "uv 那条排在标准库那条前面——照着做的人会先撞上没装的工具：\n" + message)
