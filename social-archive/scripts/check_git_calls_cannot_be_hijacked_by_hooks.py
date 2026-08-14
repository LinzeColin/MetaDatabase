#!/usr/bin/env python3
"""起 git 子进程的地方，必须自己决定环境（2026-08-07）。

## 为什么

git 钩子会把 `GIT_DIR` / `GIT_INDEX_FILE` / `GIT_WORK_TREE` 塞进环境。
子进程继承之后**会去问那个仓，而不是 `cwd=` 指的这个**——cwd 压不过 GIT_DIR。

2026-08-07 一天之内踩了三次，症状一模一样：**单独跑是绿的，pre-commit 里红**。
· `check_the_shipped_package_is_the_committed_code.py` 的 `git show`
· 它的判据里那句 `git show`
· `test_deploy_rechecks_the_tree_after_the_drills.py` 的 `git ls-files`

而仓里 2026 年更早已经为同一件事栽过一次，教训就写在
`test_docs_do_not_send_you_to_a_missing_script.py` 里（`_CLEAN_GIT_ENV`）。
**写下来没有用，得有人拦。**

最坏的一种不是红，是**静悄悄读了另一个仓**：那时候数是出得来的，只是错的。

## 规则

起 git 的调用必须**显式带 `env=`**——洗过的也好，`env=None`（明确要继承）
也好，重点是**有人做过这个决定**。裸调用一律算漏。

`env=None` 也放行，是因为有一份判据**故意**带着脏环境跑
（它测的正是检查器自己漏没漏这一步）。把「故意」和「忘了」分开的办法是
让它写出来，而不是让这道门去猜。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = ("scripts", "tests", "src")
RUNNERS = {"run", "check_output", "check_call", "Popen", "call"}


def _is_git_argv(node: ast.AST) -> bool:
    """这个调用起的是 git 吗——列表首元素、shell 字符串、`bash -c` 三种都算。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip().startswith("git ")
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.Constant) and isinstance(v.value, str)
                   and ("git " in v.value) for v in node.values)
    if isinstance(node, (ast.List, ast.Tuple)):
        parts = [e for e in node.elts]
        if parts and isinstance(parts[0], ast.Constant) and parts[0].value == "git":
            return True
        # `["bash", "-c", "... git ..."]` / f-string 同理
        if parts and isinstance(parts[0], ast.Constant) and parts[0].value in {"bash", "sh", "zsh"}:
            return any(_is_git_argv(e) for e in parts[1:])
    return False


def offenders(source: str, filename: str) -> list[str]:
    """**纯函数**，好拿片段喂它证明它真的会红。"""
    found: list[str] = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in RUNNERS
                and isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue
        if not node.args or not _is_git_argv(node.args[0]):
            continue
        if any(keyword.arg == "env" for keyword in node.keywords):
            continue
        found.append(f"{filename}:{node.lineno}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="起 git 的地方必须自己决定环境")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root)

    files = [p for directory in SCANNED for p in sorted((root / directory).rglob("*.py"))]
    bad: list[str] = []
    git_calls = 0
    for path in files:
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as error:
            print(f"  **不合格**：{rel} 解析不了：{error}")
            return 1
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in RUNNERS
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.args and _is_git_argv(node.args[0])):
                git_calls += 1
        bad.extend(offenders(source, rel))

    print(f"扫了 {len(files)} 份 .py，其中 {git_calls} 处起 git 的子进程")
    # **先证明数得到东西。** 扫到 0 个 git 调用的门永远是绿的。
    if git_calls < 5:
        print(f"  **不合格**：只数到 {git_calls} 处 git 调用——这道门在空扫，"
              "扫描范围或识别方式坏了")
        return 1
    if bad:
        for item in bad:
            print(f"  **不合格**：{item} 起了 git 却没写 env=")
        print("  ↳ git 钩子会塞 GIT_DIR，子进程会去问**那个**仓，cwd 压不过它。")
        print("    洗掉钩子那几个变量，或者显式写 env=None 表示「就是要继承」。")
        return 1
    print("每一处起 git 的地方都自己决定了环境。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
