r"""不许为一次必然失败的同步去打开他的浏览器页面（2026-08-20）。

## Owner 的原话

> 「为什么现在我的电脑每天 8 点都会自己打开并关闭小红书抖音bilibili，这是恶性bug」

那是扩展的 6 小时定时同步：它为每个已连接账号开一个后台标签页去读，读完关掉。
问题不在「开了页面」，在**那一趟必然什么也读不到**：

    B站    服务端 v0.0.0.105 起自己就能读公开收藏夹 → 浏览器那趟纯属重复
    抖音    主机授权没给到 → 读取器进不去页面，必然 PLATFORM_PERMISSION_MISSING
    小红书  同上

**零收益、纯骚扰**，而且他不知道那是什么，以为电脑中了东西。

## 这道判据钉两件

1. `server_handled` 必须把「服务端也能自己读」的平台算进去 —— 否则扩展照旧
   每天为 B 站开一次页，而那一趟读回来的东西服务端早已经有了。
2. 同步在开标签页**之前**必须先查主机授权 —— 缺授权就报错返回，不开页面。
   授权那一下要用户手势，同步这一刻补不回来，所以唯一正确的动作是**别打扰他**。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

BG = ROOT / "apps/browser-extension/background.js"


def _code() -> str:
    text = BG.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("//"))


def test_服务端能自己读的平台要算进_server_handled() -> None:
    import ast  # noqa: PLC0415

    source = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "SERVER_ALSO_READS" in names, (
        "api.py 里没有用到 SERVER_ALSO_READS —— server_handled 只看 "
        "SERVER_ACCOUNT_CONNECTORS 的话，B 站每天还会被扩展开一次页，"
        "而那一趟读回来的东西服务端早已经有了。")
    # 那一行必须真的把两个集合并起来，不是只提到名字
    assert re.search(r"server_handled.*SERVER_ACCOUNT_CONNECTORS\s*\|\s*SERVER_ALSO_READS", source), (
        "server_handled 那一行没有把两个集合并起来")


def test_开标签页之前必须先查授权() -> None:
    """**顺序就是有没有骚扰。**

    查在后面等于先开了页再发现没用 —— 他看到的就是「自己打开又关掉」。

    判法：取「同步这条路准备开页」的那一段窗口
    （`let tabOpenedByUs = false;` 到 `tabOpenedByUs = true;`），
    授权检查必须**落在这个窗口里**。前一版我写的是「存在某个建页调用在检查之后」，
    拿反例一跑没红 —— 因为连接账号那条路也有一个建页调用，永远满足那个条件。
    **判据第三次守错口径了，改成窗口包含关系。**
    """
    code = _code()
    left = code.find("let tabOpenedByUs = false;")
    right = code.find("tabOpenedByUs = true;", left + 1)
    assert left != -1 and right != -1, "找不到同步那条路的建页窗口——这道判据的前提变了"
    window = code[left:right]
    assert "permissionState(account.platform)" in window, (
        "同步路径上、在开标签页之前没有查主机授权。\n"
        "  后果就是 Owner 报的那件事：每天早上他的 Chrome 自己打开又关掉\n"
        "  小红书/抖音/B站——而那一趟因为没授权必然什么也读不到。")


def test_缺授权要报出可点的下一步() -> None:
    """报错里必须指向他**真的点得到**的那颗按钮（v0.0.0.107 加的「去授权」）。

    这个仓栽过「错误提示指向一个不存在的出口」：那时那句话让他去插件的账号页，
    而按钮在资料库的「管理账号」里。
    """
    code = _code()
    block = re.search(r"permissionState\(account\.platform\).{0,900}", code, re.S)
    assert block, "找不到那段"
    text = block.group(0)
    assert "PLATFORM_PERMISSION_MISSING" in text, "没有给出失败码"
    assert "管理账号" in text and "去授权" in text, (
        "报错没有指向资料库「管理账号」里那颗「去授权」—— "
        "而那是 v0.0.0.107 之后他真正点得到的地方")
