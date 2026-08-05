#!/usr/bin/env python3
"""突变探针：把判据断言的那个字面量从源码里删掉，看判据会不会红。

断言绿着不代表它在守什么。**唯一的证明是把它守的东西弄坏，它必须变红。**

## 归属是这个工具的全部难点

第一版靠「判据文件里出现过哪些源码路径字面量」去猜验的是哪个文件。
2026-08-05 实测：约 70 次突变报出 7 处「没守住」，**7 处全是它自己猜错了文件**
（`umask 0007` 的断言打的是 container-entrypoint.sh，它去删了只在注释里提过
一次的 prepare_systemd_host.sh；`HttpOnly` 的断言打的根本不是仓里的文件，
是 Python 标准库）。误报率 100%。

现在改成**跟着变量走**：用 ast 解析判据文件，追

    源 = (ROOT / "apps/x.js").read_text(...)      # 直接读
    源 = 某个模块级常量.read_text(...)             # 常量指向的路径
    块 = js_function(源, "...") / py_function(源, "...")   # 切片继承来源
    块 = 源.split(...)[...] / code_only(源)                # 同上

追不到就**跳过**，不猜。猜出来的归属会把「探针认错文件」报成「判据没守住」，
而那种报告比没有报告更坏。

**作用域按判据函数分。** 拉平成一张表会让后面某个判据里的 `block = ...`
覆盖掉前面同名变量的来源——实测因此把 background.js 的断言记成了
cookie-export.js 的。block / code / text / body 这些名字在判据文件里到处都是，
拉平必然错。

## 改对之后的实测（2026-08-05）

    突变 236 次 · 承重 236 · 报「没守住」0 · 归属追不到 74 · 耗时 123 秒

**每一条能追到归属的断言都是承重的。** 误报从 7 降到 0。

## 当天晚些时候重跑（判据从 ~600 涨到 965 之后）

    候选 377 · 突变 299 · 承重 299 · 报「没守住」0 · 归属追不到 78

**那 78 条不是原理上追不到，是少走了一步。** 让它报出「追不到的是哪些」
之后，78 条全指向 `background.js`、`popup.js` 这类**光秃秃的文件名**——
成因是判据里最常见的写法：

    EXT = ROOT / "apps/browser-extension"
    source = (EXT / "background.js").read_text(...)

`_path_from` 遇到 `EXT / "..."` 时左边是个 Name、追不动，就只返回了
`"background.js"`。把常量表传进去之后：

    候选 379 · 突变 355 · **承重 355** · 报「没守住」0 · 归属追不到 24

**多验了 56 条，仍然一条「没守住」都没有。** 剩下那 24 条是另一回事：
它们来自 `for text, name in ((pwa, "app.js"), ...)` 这种循环——
那个字面量是**标签**，不是路径。追它就得靠猜，所以照实报「跳过」。

**仍然是 0。** 顺带修了这个脚本自己的一处静默截断：默认预算是 40，
而输出里从来没说过那是个上限——`"load_bearing": 40` 读起来就是
「全查过了，全承重」，实际只覆盖了 377 条候选里的 11%。
我自己就差点拿一次被截断的运行去和上面那次 236 的完整运行比，
当成「覆盖悄悄掉了」去查。现在报告会说清 候选多少、跑了多少、
以及**「预算用完」与「归属追不到」是两回事**。

## 为什么仍然不挂进 pre-commit

不是因为慢（123 秒还能接受），是因为**它会写源码文件**：每次突变都要把
被测文件改坏、跑完再还原。放进每次提交都会跑的钩子里，等于让每次提交
都有一个「跑到一半被 Ctrl-C 就留下一个改坏的源文件」的窗口。
本会话已经因为「判据改仓里的文件」吃过一次无法归因的偶发失败。

所以它是**手动/定期工具**：改完一批判据之后跑一次。

用法：`python3 scripts/probe_guards_are_load_bearing.py [突变次数上限]`

**它不是发布门**：跑一次要几十分钟（每次突变都要起一次 pytest），
而且只覆盖 `assert "字面量" in 变量` 这一种形状。改完一批判据之后手动跑。
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(".")
INHERITING_CALLS = {"js_function", "py_function", "run_diagnosis_body",
                    "install_net_observer_body", "js_function_body", "code_only",
                    "after_unique", "read"}


def _path_from(node: ast.AST, constants: dict[str, str] | None = None) -> str | None:
    """从 `ROOT / "apps/x.js"` 这种表达式里取出那个相对路径。

    **左边是个变量时也要能追。** 判据里最常见的写法是

        EXT = ROOT / "apps/browser-extension"
        source = (EXT / "background.js").read_text(...)

    第一版遇到 `EXT / "background.js"` 时，左边是个 Name、追不动，
    于是只返回 `"background.js"`——一个不存在的路径。那 78 条
    「归属追不到」全是这么来的：**不是原理上追不到，是少走了一步**。
    这 78 条里有 31 条指向 background.js，而它正是本版本改得最多的文件。
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = node.right
        if isinstance(right, ast.Constant) and isinstance(right.value, str):
            left = _path_from(node.left, constants)
            return f"{left}/{right.value}" if left else right.value
    if isinstance(node, ast.Name) and constants:
        return constants.get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _sources_in(tree: ast.AST, constants: dict[str, str],
                path_funcs: dict[str, str] | None = None) -> dict[str, str]:
    """变量名 → 它读的是哪个源文件。追不到的变量不进这张表。"""
    found: dict[str, str] = {}
    # **局部的路径变量也要能查。** `root = _extension_root()` 之后，
    # `(root / "background.js")` 里的 root 只有在这张表里才追得动。
    paths = dict(constants)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        # x = _some_root()  —— 零参 helper 返回的路径
        if (path_funcs and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name) and value.func.id in path_funcs):
            paths[target.id] = path_funcs[value.func.id]
            continue
        # x = ROOT / "apps/..."  —— 局部的纯路径赋值
        if isinstance(value, ast.BinOp):
            local_path = _path_from(value, paths)
            if local_path and "/" in local_path:
                paths[target.id] = local_path
                continue
        # x = <路径表达式>.read_text(...)
        if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                and value.func.attr == "read_text"):
            base = value.func.value
            # 常量表要传进去：`(EXT / "background.js").read_text()` 里的 EXT
            # 只有查表才知道是 apps/browser-extension。
            path = _path_from(base, paths)
            if path is None and isinstance(base, ast.Name):
                path = paths.get(base.id)
            if path:
                found[target.id] = path
                continue
        # x = js_function(y, ...) / y.split(...)[...] —— 继承 y 的来源
        origin = _origin_of(value, found)
        if origin:
            found[target.id] = origin
    return found


def _origin_of(value: ast.AST, known: dict[str, str]) -> str | None:
    for node in ast.walk(value):
        if isinstance(node, ast.Name) and node.id in known:
            return known[node.id]
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in INHERITING_CALLS):
            for argument in node.args:
                if isinstance(argument, ast.Name) and argument.id in known:
                    return known[argument.id]
    return None


def _path_returning_functions(tree: ast.AST, constants: dict[str, str]) -> dict[str, str]:
    """模块级里 `def _x(): return <路径表达式>` 这种小helper → 它返回的路径。

    **判据文件里最常见的第二种写法。** 比如：

        def _extension_root() -> Path:
            return Path(__file__).parents[2] / "apps/browser-extension"

        def test_...():
            root = _extension_root()
            background = (root / "background.js").read_text(...)

    没有这一步的话，`root` 追不到，于是 `root / "background.js"` 只剩下
    `"background.js"`——一个不存在的路径，报成「归属追不到」。
    2026-08-06 实测：24 条追不到里，**全部**是这一种。
    """
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.args.args or node.args.kwonlyargs:
            continue                      # 只认零参的：带参数的返回什么要看调用点
        body = [s for s in node.body if not isinstance(s, ast.Expr)]  # 跳过 docstring
        if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
            continue
        path = _path_from(body[0].value, constants)
        if path and "/" in path:
            out[node.name] = path
    return out


def _module_constants(tree: ast.AST) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            path = _path_from(node.value, constants)
            if path and "/" in path:
                constants[node.targets[0].id] = path
    return constants


def _claims(test: pathlib.Path) -> list[tuple[str, str, str]]:
    """判据里每一处 `assert "字面量" (not) in 变量` → (字面量, 源文件, 正向还是反向)。"""
    tree = ast.parse(test.read_text(encoding="utf-8"))
    constants = _module_constants(tree)
    path_funcs = _path_returning_functions(tree, constants)
    out: list[tuple[str, str, str]] = []
    # **一个判据函数一份作用域。**
    #
    # 原来是整份文件拉平成一张表，于是后面某个判据里的 `block = ...`
    # 会把前面那个同名变量的来源覆盖掉——实测把 background.js 的断言
    # 记成了 cookie-export.js 的。同名局部变量在判据文件里到处都是
    # （block / code / text / body），拉平必然错。
    functions = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for function in functions:
        module_level = {k: v for k, v in _sources_in_module_body(tree, constants).items()}
        scope = {**module_level, **_sources_in(function, constants, path_funcs)}
        out.extend(_asserts_in(function, scope))
    return out


def _asserts_in(function: ast.AST, scope: dict[str, str]) -> list[tuple[str, str, str]]:
    """`assert "字面量" in 变量` 与 `not in` 两种都收。

    **反向那种此前一条都没验过，而它守的恰恰是最贵的几条**：
    `"chown -R" not in code`（那次把十二个密钥的属组改掉、/health 全程 200
    的事故）、`"--delete" not in rsync`（远端我自己留的备份）。
    「删掉的东西不许回来」这类判据，不验就只是一句愿望。
    """
    out: list[tuple[str, str, str]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Assert):
            continue
        test_node = node.test
        if not (isinstance(test_node, ast.Compare) and len(test_node.ops) == 1
                and isinstance(test_node.ops[0], (ast.In, ast.NotIn))):
            continue
        kind = "in" if isinstance(test_node.ops[0], ast.In) else "not_in"
        left, right = test_node.left, test_node.comparators[0]
        if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
            continue
        if not (isinstance(right, ast.Name) and right.id in scope):
            continue
        if len(left.value) < 8:
            continue
        out.append((left.value, scope[right.id], kind))
    return out


def _sources_in_module_body(tree: ast.Module, constants: dict[str, str]) -> dict[str, str]:
    """只看模块最外层的赋值，不下钻进任何函数。"""
    shell = ast.Module(body=[n for n in tree.body if isinstance(n, ast.Assign)], type_ignores=[])
    return _sources_in(shell, constants)


def main() -> int:
    # **默认只跑 40 次，而输出里从来没说过这是个上限。**
    #
    # 2026-08-05：我不带参数跑了一次，看到 `"load_bearing": 40`，
    # 又想起文档里记着的那次是 236——差点当成「这道探针的覆盖悄悄掉了」去查。
    # 它没掉，是我拿一次**被截断的**运行去比一次完整运行。
    #
    # 报告里不说「40 是上限、一共有多少条候选」，读起来就是「全查过了，全承重」。
    # **静默截断读起来和「覆盖完整」一模一样**，这正是这个项目反复在拆的那种话。
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    requested = budget
    candidates = 0
    # **只报一个数字「追不到 78 条」，等于没报。**
    # 没人能从那个数字看出「这 78 条是没人守，还是这道探针够不着」。
    results: dict = {"load_bearing": 0, "not_load_bearing": [],
                     "unresolved": 0, "unresolved_detail": []}
    for test in sorted(pathlib.Path("tests/focused").glob("test_*.py")):
        try:
            candidates += len(dict.fromkeys(_claims(test)))
        except SyntaxError:
            pass
    for test in sorted(pathlib.Path("tests/focused").glob("test_*.py")):
        if budget <= 0:
            break
        try:
            claims = _claims(test)
        except SyntaxError:
            continue
        for literal, relative, kind in dict.fromkeys(claims):
            if budget <= 0:
                break
            source = ROOT / relative
            if not source.is_file():
                results["unresolved"] += 1
                results["unresolved_detail"].append(
                    {"test": test.name, "source": relative, "why": "指向的文件不在"})
                continue
            original = source.read_text(encoding="utf-8")
            if kind == "in":
                mutated = "\n".join(l for l in original.splitlines() if literal not in l)
                if mutated == original:
                    # **删不掉 = 这条断言的字面量在那个文件里根本不出现。**
                    # 多半是归属追错了文件，或者断言的是行为而不是字面量。
                    results["unresolved"] += 1
                    results["unresolved_detail"].append(
                        {"test": test.name, "source": relative,
                         "literal": literal[:60], "why": "那个文件里找不到这个字面量"})
                    continue
            else:
                # **反向判据的突变是「把它塞回去」。**
                # 原样附在文件末尾，不加注释符号——很多判据会先剥注释再查
                # （deploy 那条就是 `code_only()`），塞成注释等于没塞。
                if literal in original:
                    # **多半不是判据错了，是它查的不是整份文件。**
                    # 实例：`"chown -R" not in code`，而 code 是剥掉注释之后的文本——
                    # 那句 `chown -R` 就写在解释事故的注释里。原文里有、判据看的那份里没有。
                    results["unresolved"] += 1
                    results["unresolved_detail"].append(
                        {"test": test.name, "source": relative, "literal": literal[:60],
                         "why": "原文里已经有这个字面量了——判据多半查的是过滤/切片之后的文本，这种插法证不了它"})
                    continue
                mutated = original + "\n" + literal + "\n"
            budget -= 1
            source.write_text(mutated, encoding="utf-8")
            try:
                run = subprocess.run([sys.executable, "-m", "pytest", str(test), "-q", "-x"],
                                     capture_output=True, text=True, timeout=180)
                output = (run.stdout or "") + (run.stderr or "")
                red = run.returncode != 0
                # **红了还不够，得是「断言没过」那种红。**
                #
                # 反向突变是往文件里塞文本，那可能把 yaml/json 解析弄崩、
                # 或者让别的判据抛异常——那种红不证明这条判据守住了什么，
                # 它只证明我把文件弄坏了。只认 AssertionError。
                asserted = "AssertionError" in output or "assert" in output
            finally:
                source.write_text(original, encoding="utf-8")
            if red and asserted:
                results["load_bearing"] += 1
            elif red:
                results["unresolved"] += 1
                results["unresolved_detail"].append(
                    {"test": test.name, "source": relative, "literal": literal[:60], "kind": kind,
                     "why": "突变之后判据是因为别的错误红的（不是断言没过），这条不算验到"})
            elif kind == "not_in":
                # **绿了不代表这条判据是摆设。**
                #
                # 反向突变是把字面量附在**文件末尾**，而判据常常只看文件里的一小段：
                #   overflow = background.split("…NET_CAPTURE_LIMIT", 1)[1][:200]
                #   assert "netCaptureBuffer.shift()" not in overflow
                # 塞在末尾根本进不了那 200 个字符，判据当然不红——**它没错，是我够不着**。
                #
                # 2026-08-06 差点把这一条报成「没守住」。手工把 shift() 塞进它自己
                # 那个窗口里，判据当场就红了。所以这里只报「证不了」，不报「没守住」。
                results["unresolved"] += 1
                results["unresolved_detail"].append(
                    {"test": test.name, "source": relative, "literal": literal[:60], "kind": kind,
                     "why": "反向突变塞在文件末尾；判据若只看文件里的一小段就够不着，**这不等于它是摆设**"})
            else:
                results["not_load_bearing"].append(
                    {"test": test.name, "source": relative, "literal": literal, "kind": kind})
    attempted = results["load_bearing"] + len(results["not_load_bearing"])
    results["mutation_budget"] = requested
    results["candidates_found"] = candidates
    # **「预算用完」和「归属追不到」是两回事，别混成一句。**
    #
    # 第一版把两者都算成「没跑到」，于是一次预算充足的完整运行
    # （299 突变 + 78 追不到 = 377 全看过）被描述成「只突变了 299 条」，
    # 读起来像被截断了。指错原因，今天第七次。
    truncated = results["unresolved"] + attempted < candidates
    results["coverage_zh"] = (
        f"**预算用完了**：只突变了 {attempted} 条，候选有 {candidates} 条"
        f"（上限 {requested}，命令行第一个参数可以调）。没跑到的不是「通过」，是没查。"
        if truncated else
        f"{candidates} 条候选全看过了：{attempted} 条做了突变验证，"
        f"{results['unresolved']} 条**追不到归属所以跳过**——"
        "跳过不是通过，那几条这道探针管不了。"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
