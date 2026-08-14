r"""每个 `scripts/check_*.py` 都得有人调（2026-08-14）。

## 它修的是什么

这个仓的原则写在 `AGENTS.md` 和好几道 `find_*` 里：**建好了没接上等于没建**。
而这一类里最隐蔽的一种是**判据自己成了孤儿**——它还在、还能跑、看着像在守着什么，
而流程里没有任何地方会叫它。

2026-08-14 数了一遍：29 个 `check_*.py` 里有 1 个没人调，
`check_the_backup_really_restores.py`（150 行，8-11）。
它被 `check_the_backup_can_actually_be_restored.py`（294 行，8-12，已挂在部署里）
**严格覆盖**了：后者除了运行库还验 private-database 和 disaster-recovery，
部署日志里逐行印着「runtime-db：3/3 份真取回来了」。零引用、零文档指向。

**留着一个被取代的判据是陷阱**：接手的人（或 AI）可能去跑它、拿到一个
和流程不同的答案；更坏的是去**修它**，而真正在守门的是另一个。
所以那一个删掉了（git 历史里还在），并立这道门防止再长出来。

## 口径

- 只管 `scripts/check_*.py`。`find_*.py` 当天全部有调用方，
  但也一并纳入——它们和 check 一样是"跑起来才有用"的东西。
- 「有人调」= 出现在 `final_verify.py`、`deploy_to_production.sh`，
  或 `tests/` 里任意一份。**测试里被调也算**：那说明至少有东西会执行它。
- 真有"故意留着不接进流程"的，写进 `DELIBERATELY_STANDALONE` 并**说清理由**——
  不写理由的白名单等于给自己一个随手放行的口子。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 故意不接进流程的，每一条都要写清为什么
DELIBERATELY_STANDALONE: dict[str, str] = {}


def _strip_docs(source: str) -> str:
    """剥掉 docstring 和 `#` 注释。

    **不剥的话这道门是瞎的。** 2026-08-14 实测：把被删掉的孤儿放回去，
    这道门**照样绿**——因为本文件的 docstring 里就写着那个孤儿的文件名，
    而调用方文本扫的正是 `tests/**`。于是它永远找得到"调用方"。
    推广开：**任何被我写进说明里的孤儿，这道门都看不见。**
    （今天第九次「我写的说明打中/废掉我自己的判据」。）

    说明里提到一个脚本名 ≠ 有人调用它。`ast` 里没有注释，
    docstring 又能精确定位到行，所以这两样一起剥得干净。
    """
    import ast  # noqa: PLC0415

    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                for i in range(first.lineno - 1, (first.end_lineno or first.lineno)):
                    if 0 <= i < len(lines):
                        lines[i] = ""
    return "\n".join(line.split("#", 1)[0] for line in lines)


def _callers_text() -> str:
    parts = []
    for rel in ("scripts/final_verify.py", "scripts/deploy_to_production.sh"):
        path = ROOT / rel
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            parts.append(_strip_docs(raw) if path.suffix == ".py"
                         else "\n".join(l.split("#", 1)[0] for l in raw.splitlines()))
    for path in (ROOT / "tests").rglob("*.py"):
        parts.append(_strip_docs(path.read_text(encoding="utf-8", errors="replace")))
    return "\n".join(parts)


def _gate_scripts() -> list[str]:
    names = [p.name for p in (ROOT / "scripts").glob("check_*.py")]
    names += [p.name for p in (ROOT / "scripts").glob("find_*.py")]
    return sorted(names)


def test_每个判据都有人调() -> None:
    scripts = _gate_scripts()
    assert scripts, (
        "一个 check_*/find_* 都没扫到。目录结构变了就把这里一起改——"
        "否则这道判据会对着空集合永远绿。")

    callers = _callers_text()
    assert callers, "读不到调用方文件，这道门此刻判不了任何东西"

    orphans = [
        name for name in scripts
        if name not in DELIBERATELY_STANDALONE and name not in callers
    ]
    assert not orphans, (
        f"这几个判据没有任何地方会叫它：{orphans}\n"
        "  它还在、还能跑、看着像在守着什么，而流程里没人调——**等于没建**。\n"
        "  更坏的是接手的人可能去修它，而真正在守门的是另一个。\n"
        "  要么接进 final_verify.py / deploy_to_production.sh，要么删掉，\n"
        "  要么写进 DELIBERATELY_STANDALONE 并说清为什么故意不接。")


def test_白名单每一条都写了理由() -> None:
    blank = [k for k, why in DELIBERATELY_STANDALONE.items() if not str(why).strip()]
    assert not blank, f"这几条登记成故意独立却没写理由：{blank}"


def test_这套检测本身还能判() -> None:
    """**拿已知答案自检。** 调用方文本读空时上面那条会把全部判据报成孤儿（假阳），
    脚本目录读空时会全绿（假阴）——两头都要先排除。"""
    callers = _callers_text()
    assert "check_docs_point_at_things_that_exist.py" in callers, (
        "连一个确定被调用的判据都在调用方文本里找不到——读错文件了")
    # **负对照要在运行时拼出来。** 写成字面量的话它就出现在这个文件里，
    # 而 `_callers_text()` 扫的正是 `tests/**`——于是负对照命中它自己。
    # （今天第八次「我写的东西打中我自己的判据」。）
    never = "check_" + "no_such_gate_" + "9f3a2b.py"
    assert never not in callers, "负对照命中了——扫描集或拼法有问题"
    assert len(_gate_scripts()) >= 20, f"只扫到 {len(_gate_scripts())} 个判据，太少，八成是路径错了"
