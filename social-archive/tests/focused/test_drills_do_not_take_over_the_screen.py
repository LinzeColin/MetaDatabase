"""演练不许抢 Owner 的屏幕（2026-08-07）。

他的原话：**「为什么你永远都要不停开了又关关了又开我的浏览器」**。

13 个演练每个都起一个**可见的** Chrome，一次部署跑 15 个，就是十五次
在他屏幕上弹窗又关掉；我调试时还会连跑好几遍。这些演练一个都不需要人看着——
弹出来纯粹是从来没人加过 `--headless=new`。

（改完顺带发现它还更快：save_page 12.8s→6.0s，routing 9.6s→3.9s。）

这条判据钉住的是：**只要一个演练会起 Chrome，它就必须默认无头。**
调试时设 `SA_DRILL_HEADED=1` 看得见——escape hatch 只往「看得见」那一侧开，
不允许反过来有个开关能让它默认弹窗。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _executable_lines(path: Path) -> list[str]:
    """去掉注释行与文档字符串里的行——用法示例里出现的命令行不算真的启动。"""
    import ast

    text = path.read_text(encoding="utf-8")
    docstring_lines: set[int] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text.splitlines()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        # **不是所有 body 都是列表。** `lambda x: y` 与 `a if b else c` 的 body
        # 是一个表达式，`body[0]` 直接 TypeError。第一版就栽在这儿。
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            docstring_lines.update(
                range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return [line for number, line in enumerate(text.splitlines(), 1)
            if number not in docstring_lines and not line.lstrip().startswith("#")]


def _drills_that_launch_chrome() -> list[Path]:
    found = []
    for path in sorted((ROOT / "scripts").glob("*_drill.py")):
        if any("--remote-debugging-port" in line for line in _executable_lines(path)):
            found.append(path)
    return found


def test_there_are_drills_that_launch_chrome() -> None:
    """**先证明这条判据看得见东西。** 一条数到 0 个演练的判据永远是绿的。"""
    assert len(_drills_that_launch_chrome()) >= 10, (
        "起 Chrome 的演练一个都没数到——这条判据瞎了，不是「演练都很乖」")


def test_every_chrome_drill_is_headless_by_default() -> None:
    for path in _drills_that_launch_chrome():
        lines = _executable_lines(path)
        assert any("--headless=new" in line for line in lines), (
            f"**{path.name} 会弹出一个可见的 Chrome。**\n"
            "他说过「为什么你永远都要不停开了又关关了又开我的浏览器」——"
            "演练不需要人看着，加上 `--headless=new`（调试时 SA_DRILL_HEADED=1）")


def test_the_escape_hatch_only_opens_towards_visible() -> None:
    """**开关只能往「看得见」那一侧拨。**

    反过来的开关（一个能让它默认弹窗的环境变量）迟早会被谁设上，
    然后他的屏幕又开始被抢——而那时没有任何判据会红。
    """
    for path in _drills_that_launch_chrome():
        for line in _executable_lines(path):
            if "--headless=new" not in line:
                continue
            assert "SA_DRILL_HEADED" in line, (
                f"{path.name} 的无头开关不是 SA_DRILL_HEADED——"
                "换个名字就没人知道怎么调试，也没法统一钉住")
            # 形如：`[] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]`
            # 即：**设了才看得见**，默认无头。
            assert line.index("SA_DRILL_HEADED") < line.index("--headless=new"), (
                f"{path.name}：判断写反了，默认会变成弹窗")
