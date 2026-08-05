"""版本只有一个真源，其他地方都得跟它一样（v0.0.0.7 / T18）。

2026-08-05 数了一遍全仓文档提到的版本号，数出三处不成立的事实：
README 第 1 行说 v0.0.0.6、AGENTS.md 第 9 行说 v0.0.0.6、
CHANGELOG 最新一节停在 v0.0.0.4（v5/v6/v7 三版一条都没有）。

**没有一处是「坏了」的样子。** 改版本号时，代码里那几处会因为跑不起来
而被发现，文档里这几处不会——它们只会安静地说一个两版之前的事实。

而 `AGENTS.md` 是**接手的 agent 读的那一份**：它说错，后面每一个人
都会被告知一个错的版本。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_the_stated_version_is_the_real_one.py"


def _run(root: Path | None = None) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(CHECK)]
    cwd = root or ROOT
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def _sandbox(tmp_path: Path, version: str = "9.9.9", **overrides) -> Path:
    """造一份最小的假仓，**绝不改仓里的真文件**。

    本会话已经因为「判据改仓里的文件」吃过一次无法归因的偶发失败：
    跑到一半被打断就留下一个改坏的文件，两次同时跑还会互相踩。
    """
    stated = {
        "pyproject.toml": f'[project]\nversion = "{version}"\n',
        "src/social_archive/__init__.py": f'"""x"""\n__version__ = "{version}"\n',
        "apps/browser-extension/manifest.json": json.dumps({"version": version}),
        "README.md": f"# Social Archive v{version}\n",
        "AGENTS.md": f"## 唯一身份\n\n- 版本：`v{version}`\n",
        "CHANGELOG.md": f"# Changelog\n\n## v{version} — x\n",
    }
    stated.update(overrides)
    for name, text in stated.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts/check_the_stated_version_is_the_real_one.py").write_text(
        CHECK.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def _run_in(sandbox: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(sandbox / "scripts/check_the_stated_version_is_the_real_one.py")],
        cwd=sandbox, capture_output=True, text=True, check=False)


def test_the_real_repo_passes_right_now() -> None:
    done = _run()
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_consistent_sandbox_passes(tmp_path) -> None:
    """**先验它会绿。** 一个永远喊红的门等于没有门。"""
    done = _run_in(_sandbox(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr


def test_it_catches_agents_md_stating_an_old_version(tmp_path) -> None:
    """**这一处是最要紧的**：AGENTS.md 是接手的 agent 读的那一份。"""
    done = _run_in(_sandbox(tmp_path, **{"AGENTS.md": "## 唯一身份\n\n- 版本：`v0.0.0.6`\n"}))
    assert done.returncode != 0, "AGENTS.md 说了个旧版本，这道门却放过了"
    assert "AGENTS.md" in done.stdout


def test_it_catches_the_readme_title(tmp_path) -> None:
    done = _run_in(_sandbox(tmp_path, **{"README.md": "# Social Archive v0.0.0.1\n"}))
    assert done.returncode != 0, "README 标题写了个旧版本，这道门却放过了"
    assert "README.md" in done.stdout


def test_it_catches_the_extension_manifest(tmp_path) -> None:
    """Owner 装的那个扩展报的版本——他截图给你看的就是这个数。"""
    done = _run_in(_sandbox(tmp_path, **{
        "apps/browser-extension/manifest.json": json.dumps({"version": "0.0.0.6"})}))
    assert done.returncode != 0, "扩展 manifest 落后一版，这道门却放过了"
    assert "manifest.json" in done.stdout


def test_it_catches_a_changelog_with_no_entry_for_this_version(tmp_path) -> None:
    """三个版本没有条目时，翻的人只会以为最后一次改动是 v0.0.0.4。"""
    done = _run_in(_sandbox(tmp_path, **{"CHANGELOG.md": "# Changelog\n\n## v0.0.0.4 — x\n"}))
    assert done.returncode != 0, "CHANGELOG 里没有这一版，这道门却放过了"
    assert "CHANGELOG.md" in done.stdout


def test_a_declaration_that_disappeared_is_caught_too(tmp_path) -> None:
    """把那一行删掉也得红——否则「删掉它」就成了绕过这道门的办法。"""
    done = _run_in(_sandbox(tmp_path, **{"AGENTS.md": "## 唯一身份\n\n- 产品：Social Archive\n"}))
    assert done.returncode != 0, "版本声明整行没了，这道门却放过了"
    assert "找不到版本声明" in done.stdout


def test_mentioning_an_old_version_in_prose_is_not_an_error(tmp_path) -> None:
    """「v0.0.0.6 当时是这么做的」是历史叙述，不是错。

    这道门只查**声明版本**的地方。查得太宽的话，每一条历史记录都会点红它，
    最后只能靠把门关掉来收场。
    """
    sandbox = _sandbox(tmp_path)
    (sandbox / "docs").mkdir(exist_ok=True)
    (sandbox / "docs/旧事.md").write_text(
        "v0.0.0.6 当时把 worker 拆成三个，后来证伪删掉了。\n", encoding="utf-8")
    done = _run_in(sandbox)
    assert done.returncode == 0, done.stdout + done.stderr


def test_it_is_wired_into_the_release_gate() -> None:
    """**建好了没接上**是这个项目最常见的失败形态，这道门自己不能是第七次。"""
    text = (ROOT / "scripts/final_verify.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    assert "check_the_stated_version_is_the_real_one.py" in code, (
        "这道门没被发布门调用——只在注释里提到不算"
    )
