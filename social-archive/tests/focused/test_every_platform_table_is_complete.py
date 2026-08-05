"""平台表不许漏平台，**而且不许靠我记得有几张**（v0.0.0.7 / T06）。

给 youtube 接入口这一件事上，「我以为已经查全了，又冒出一张表」发生了四次，
**每一次都是宣布完成之后才发现的**：

  1. 「开 B 站时顺手连一下」—— 方向就错了，硬边界禁止
  2. 「两个方向都封住了」—— 漏 platform-catalog.js，中文名退回内部 id
  3. 四张表全绿之后 —— 漏 options.js 的 platformOrder，
     **设置页不出卡片，交接里让 Owner 点的那个按钮根本不存在**
  4. 补完之后又扫出四张 —— popup ×2、sidepanel ×2、options 的 relationCopy

第 4 次不是我想起来的，是**改用机器扫**才捞出来的。这道门就是那次扫描。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_every_platform_table_is_complete.py"
SOURCE = CHECK.read_text(encoding="utf-8")


def _run(cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK)], cwd=cwd or ROOT,
                          capture_output=True, text=True, check=False)


def test_the_repo_passes_right_now() -> None:
    done = _run()
    assert done.returncode == 0, done.stdout + done.stderr


def test_it_catches_a_table_that_forgot_a_platform(tmp_path) -> None:
    """**先验它会红。** 造一份少了 youtube 的平台表，它必须报出来。

    这里不改仓里的文件——那种判据不可重入，跑到一半被打断就留下一个改坏的源文件。
    做法是把检查器复制进一个临时小仓，只在那儿放一张缺平台的表。
    """
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "src/social_archive").mkdir(parents=True)
    (tmp_path / "apps").mkdir()
    (tmp_path / "src/social_archive/credentials.py").write_text(
        'CUSTODIAL_PLATFORMS = frozenset({"x", "instagram", "youtube"})\n', encoding="utf-8")
    (tmp_path / "src/social_archive/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "scripts/check.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "apps/ui.js").write_text(
        'const names = { xiaohongshu:"小红书", douyin:"抖音", bilibili:"B站", x:"X" };\n',
        encoding="utf-8")
    done = subprocess.run([sys.executable, str(tmp_path / "scripts/check.py")],
                          cwd=tmp_path, capture_output=True, text=True, check=False)
    assert done.returncode != 0, "一张少了 youtube 的表，这道门却放过了"
    assert "youtube" in done.stdout, done.stdout


def test_a_complete_table_passes(tmp_path) -> None:
    """对照面：表里齐了就必须放行，否则它只是个永远喊红的门。"""
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "src/social_archive").mkdir(parents=True)
    (tmp_path / "apps").mkdir()
    (tmp_path / "src/social_archive/credentials.py").write_text(
        'CUSTODIAL_PLATFORMS = frozenset({"x", "instagram", "youtube"})\n', encoding="utf-8")
    (tmp_path / "src/social_archive/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "scripts/check.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "apps/ui.js").write_text(
        'const names = { xiaohongshu:"小红书", douyin:"抖音", bilibili:"B站", '
        'x:"X", instagram:"Instagram", youtube:"YouTube" };\n', encoding="utf-8")
    done = subprocess.run([sys.executable, str(tmp_path / "scripts/check.py")],
                          cwd=tmp_path, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_deliberate_subsets_must_carry_a_reason() -> None:
    """**允许例外，但例外必须说得出话。**

    和「已删 xxx」那条规则同一个道理：放行的门槛是写下理由，
    否则这张表会慢慢变成「凡是报错的都加进来」的静音开关。
    """
    import ast

    tree = ast.parse(SOURCE)
    subsets = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "DELIBERATE_SUBSETS" for t in node.targets):
            subsets = ast.literal_eval(node.value)
    assert isinstance(subsets, dict) and subsets, "找不到那张例外表"
    for marker, reason in subsets.items():
        assert isinstance(reason, str) and len(reason) >= 8, (
            f"{marker!r} 这条例外没写清理由：{reason!r}"
        )


def test_exemptions_are_keyed_on_the_line_not_the_table_name() -> None:
    """**platform_canary.py 里两张表都叫 `platforms`。**

    一张是全平台、一张是 all-cn 的国内子集。按表名登记就分不开这两者——
    要么一起放行（漏掉真缺失），要么一起报错（冤枉有意的子集）。
    """
    assert "marker in line for marker in DELIBERATE_SUBSETS" in SOURCE, (
        "例外还是按表名匹配的"
    )
    assert "all-cn" in SOURCE, "那张国内子集没有被登记"


def test_it_says_out_loud_what_it_cannot_see() -> None:
    """跨行的表这条规则看不到——**那不是「没有问题」，是这条规则的盲区**。

    一道门把自己的盲区说出来，和它查到什么一样重要。
    """
    assert "跨行的表会被这条规则漏掉" in SOURCE
    assert "这不是「没有问题」" in SOURCE


def test_it_is_wired_into_the_release_gate() -> None:
    text = (ROOT / "scripts/final_verify.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    assert "check_every_platform_table_is_complete.py" in code, (
        "这道门没被发布门调用——只在注释里提到不算"
    )
