#!/usr/bin/env python3
"""找出「建好了但没人用」的代码（v0.0.0.7）。

## 为什么需要它

本会话同一形态栽了**四次**：

    failure_copy.py               失败文案词典建好，没有生产调用方
    db.unexplained_zero_runs      INV-NO-SILENT-ZERO 的审计，零调用方
    SYNC_QUEUE_LAST_RESULT_KEY    background.js 里写了四处，没有界面读
    CredentialStore.materialize   凭据落盘取用，只有测试在调

四次的共同点：**模块写完了、判据写好了、全绿**——然后才发现没有人在调它。
判据只证明「这个函数写得对」，不证明「有人在调它」。第四次的代价最大：
T06 的验收在接线之前**无论谁登录都不可能通过**，而我一度把它报成
「只差 Owner 登录」。

这个脚本把「有没有调用方」变成可以一次性问完的问题。

## 判据是什么

对 `src/` 与 `scripts/` 下每个公开的顶层函数/类/方法：它的名字有没有在
**生产代码内部**出现过（定义那一行不算）。只在 `tests/` 里出现 = 没接上。

`scripts/` 算生产：systemd unit 直接跑它们。第一版漏了这一条，
把备份/复制/导出整批报成没人用——**判据自己的射程写错了，
正是它要抓的那种毛病。**

## 它一定会有误报

框架回调（FastAPI 路由、pytest fixture）、`__init__` 导出、动态调用都会被
误判。所以：**它的输出是问题清单，不是判决**。每一条要么接上，要么写进
下面的 KNOWN_ENTRYPOINTS 并说明为什么它没有仓内调用方。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# **生产代码不只有 src/。** systemd unit 直接跑 scripts/ 下的脚本，
# 那里的调用同样算「接上了」。第一版只扫 src/，把备份/复制/导出那一批
# 全报成了没人用——**判据自己的射程写错了，正是它要抓的那种毛病。**
PRODUCTION_DIRS = ("src", "scripts")

# **按设计就该没有调用方**的东西。每一条都要写清为什么。
BY_DESIGN: dict[str, str] = {
    "SourceConnector": "connectors/base.py 的结构化协议，只用于类型标注",
    "PrivateDatabaseWriter": "**故意的绊线**：本地工作树写入已废弃，这个门面存在的意义就是让残留调用当场抛错。有调用方反而是坏消息",
    "write_content_bundle": "同上，PrivateDatabaseWriter 的方法，调用即抛",
    "write_object_reference": "同上",
    "open_tab_async": "scripts/cdp_extension_harness.py 是给人手动驱动浏览器用的开发工具，不是生产路径",
    "ev": "同上",
    "redirect_request": "urllib 的框架回调：check_the_guide_warns_about_the_access_gate.py 覆写它来**不跟随跳转**（要看的正是 302 跳去哪儿）。仓内没人显式调它，调用方是 urllib 自己",
}

# **确实没接上，而且我知道**。列在这里是为了让「知道」这件事可查，
# 不是为了让检查器闭嘴。每一条要写清缺的是消费方还是产品决策。
NO_CONSUMER_YET: dict[str, str] = {
    "revoke_all": "撤销某人全部平台凭据。代码是对的，但界面上没有「断开全部」这个动作——缺的是产品决策，不是代码",
    "revoke_all_sessions": "登出全部设备。同上，界面没有这个入口",
    "ConnectorStateView": "连接器状态视图模型，当前接口直接回字典，没走这个模型",
}

KNOWN_ENTRYPOINTS: dict[str, str] = {**BY_DESIGN, **NO_CONSUMER_YET}

SKIP_PREFIXES = ("_",)  # 私有名不查


def is_framework_registered(node: ast.AST) -> bool:
    """带装饰器的函数由框架注册（FastAPI 路由、pytest fixture 等）。

    它们**本来就没有显式调用方**，报出来只是噪音。
    """
    return bool(getattr(node, "decorator_list", None))


# 覆写基类的方法同样由框架调用（BaseHTTPRequestHandler 的 do_GET 等）。
# 判据打在**命名约定**上而不是逐个列举，否则加一个 do_OPTIONS 就漏。
OVERRIDE_PREFIXES = ("do_", "handle_", "log_")


def is_base_class_override(name: str, inside_class: bool) -> bool:
    return inside_class and name.startswith(OVERRIDE_PREFIXES)


def public_definitions(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith(SKIP_PREFIXES) and not is_framework_registered(node):
                out.append((node.name, node.lineno))
        elif isinstance(node, ast.ClassDef):
            continue
    # 类的公开方法也算——materialize 就是被这一层抓到的
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if (not item.name.startswith(SKIP_PREFIXES)
                            and item.name != "__init__"
                            and not is_framework_registered(item)
                            and not is_base_class_override(item.name, True)):
                        out.append((item.name, item.lineno))
    return out


def main() -> int:
    sources: list[Path] = []
    for folder in PRODUCTION_DIRS:
        sources.extend(sorted((ROOT / folder).rglob("*.py")))
    blob: dict[Path, str] = {p: p.read_text(encoding="utf-8") for p in sources}

    unwired: list[str] = []
    for path, text in blob.items():
        for name, lineno in public_definitions(path):
            if name in KNOWN_ENTRYPOINTS:
                continue
            pattern = re.compile(rf"\b{re.escape(name)}\b")
            hits = 0
            for other, other_text in blob.items():
                for i, line in enumerate(other_text.splitlines(), 1):
                    if other == path and i == lineno:
                        continue  # 定义那一行不算
                    if re.match(rf"\s*(async\s+)?(def|class)\s+{re.escape(name)}\b", line):
                        continue  # 其它地方的同名定义也不算
                    if pattern.search(line):
                        hits += 1
                        break
                if hits:
                    break
            if not hits:
                rel = path.relative_to(ROOT)
                unwired.append(f"  {rel}:{lineno}  {name}")

    if NO_CONSUMER_YET:
        print(f"已知没接上（{len(NO_CONSUMER_YET)} 个，非失败——但别让它悄悄变长）：")
        for name, why in sorted(NO_CONSUMER_YET.items()):
            print(f"  {name}：{why}")
        print()
    if unwired:
        print(f"生产代码里没有任何调用方、也没有登记理由的公开符号：{len(unwired)} 个")
        print("（框架回调/导出会误报——逐条判断，接上或写进 KNOWN_ENTRYPOINTS 并说明理由）")
        for line in unwired:
            print(line)
        return 1
    print("每个公开符号都至少有一处生产代码引用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
