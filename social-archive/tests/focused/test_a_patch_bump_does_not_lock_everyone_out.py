"""升一个补丁版本不许把所有已装插件判成不兼容（v0.0.0.20）。

Owner 这一轮开工时的原话是「整个软件完全不能使用」。
直接原因是安装页不讲怎么更新——那个修了。**而让它变致命的是另一行**：

    compatible: version === PRODUCT_VERSION      // 完全相等才算兼容

服务端每升一个补丁版本，所有已装插件当场全被判成不兼容，
同步、保存、连接全被挡住，直到他手动去覆盖文件。
2026-08-06 这一天升了 19 个版本——**每一次都会把他整个锁在门外**，
而我每次都报告「已修复」。修了症状，留着病根，然后在病根上跑了 19 遍。

改成「不低于服务端下发的下限」。这组判据守两件事：
闸门本身按下限判；**以及每一句讲这件事的话也说下限**
（改了闸门、漏掉旁边那句话，是这一天里第三次犯的同一个错）。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "apps/pwa/app.js"
INSTALL_HTML = ROOT / "apps/pwa/extension-install.html"


def _code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    without_blocks = re.sub(r"(?m)^[ \t]*/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(line for line in without_blocks.splitlines()
                     if not line.lstrip().startswith("//"))


def test_the_server_publishes_a_minimum_and_it_is_not_the_current_version() -> None:
    # **从源码里读，不 import api** —— 那个模块一进门就去建
    # /var/lib/social-archive，测试机上没有权限。
    api_src = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    found = re.search(r'MINIMUM_EXTENSION_VERSION = "([0-9.]+)"', api_src)
    assert found, "服务端没有定义 MINIMUM_EXTENSION_VERSION"
    minimum = found.group(1)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert minimum, "没有下限，就退回「必须完全相等」"
    # **下限不该跟着当前版本走。** 跟着走的话等于又回到相等判据，
    # 只是绕了一圈——这条断言就是防那种"顺手同步一下"的改动。
    assert minimum != version, (
        f"下限被设成了当前版本 {version} —— 那和「必须完全相等」是一回事，"
        "服务端每升一版又会把所有人锁在门外"
    )
    assert '"minimum_extension_version": MINIMUM_EXTENSION_VERSION' in api_src, (
        "常量定义了却没有下发——界面拿不到它，会退回相等判据"
    )


def test_the_gate_compares_against_the_minimum_not_equality() -> None:
    code = _code(APP_JS)
    assert "minimum_extension_version" in code, "资料库没读服务端下发的下限"
    assert "compareVersions" in code, "没有逐段比版本的函数"
    # 旧的相等判据不许再作为主判据出现
    assert "compatible: version === PRODUCT_VERSION," not in code, (
        "**相等判据还在当主判据**——服务端每升一个补丁版本就把所有人锁在门外"
    )


def test_versions_are_compared_numerically_not_as_strings() -> None:
    """`"0.0.0.9" > "0.0.0.10"` 按字符串比是**真**（'9' > '1'）。

    这一天正好跨过那个边界，所以这不是理论问题。
    """
    script = _code(APP_JS)
    start = script.index("function compareVersions")
    # **按括号取，不要按固定长度切。** 第一版切了 600 字符，
    # 正好把函数体切断，node 报 "Unexpected end of input"——
    # 判据自己坏了却像是被测代码坏了。
    opening = script.index("{", start)
    depth = 0
    end = opening
    for index in range(opening, len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    body = script[start:end]
    done = subprocess.run(
        ["node", "-e", body + """
        const cases = [["0.0.0.9","0.0.0.10",-1],["0.0.0.19","0.0.0.9",1],
                       ["0.0.0.7","0.0.0.9",-1],["0.0.0.9","0.0.0.9",0]];
        for (const [a,b,want] of cases) {
          const got = compareVersions(a,b);
          if (got !== want) { console.log(`WRONG ${a} vs ${b}: ${got} != ${want}`); process.exit(1); }
        }
        console.log("OK");
        """], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, f"版本比大小不对：{done.stdout}{done.stderr[-300:]}"


def test_every_sentence_about_it_says_the_minimum_too() -> None:
    """**改了闸门、漏掉旁边那句话**——这一天里第三次犯的同一个错。

    闸门按下限判，而提示语还在说「需要 v<当前版本>」的话，
    他会以为必须追到最新那一版，那和被锁在外面的体感是一样的。
    """
    app = _code(APP_JS)
    install = _code(INSTALL_HTML)
    assert "需要 v${PRODUCT_VERSION}" not in app, (
        "「下一步」那句还在拿当前版本当门槛说话"
    )
    assert "至少需要" in app, "资料库没有一句话说「至少需要」"
    assert "至少需要" in install, "安装页没有一句话说「至少需要」"
    # 安装页拦不拦也要按下限
    assert "minimum_extension_version" in install, "安装页没读下限，还在按相等拦"
