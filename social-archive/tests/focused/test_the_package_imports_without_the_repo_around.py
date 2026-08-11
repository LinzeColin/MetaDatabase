r"""装进镜像之后仓不在了——那时候 import 还得活着（2026-08-10）。

## 这条判据是从一次"差点全挂"来的

我给同步范围立了个真源，写法是 import 时读

    Path(__file__).resolve().parents[2] / "apps/browser-extension/content/platform-catalog.js"

在仓里 `parents[2]` 正好是仓根，**1402 条判据全绿**。
装进镜像之后 `social_archive` 在 `/usr/local/lib/python3.12/site-packages/` 下，
`parents[2]` 变成 `/usr/local/lib/python3.12/`：

    FileNotFoundError: '/usr/local/lib/python3.12/apps/browser-extension/
                        content/platform-catalog.js'

而我还特意写了「读不到就抛」，于是入口点 `social-archive-api` **死在 import 上**。
推上去就是生产全挂 + 回滚。

**判据没抓到它，因为判据全跑在仓里。** 抓到它的是把镜像真起一次。

## 所以这里把那个环境造出来

把 `src/social_archive` 整个复制到一个临时目录（外面没有 `apps/`、没有 `dist/`、
没有 `runtime/`），从**根目录**去 import 每一个模块。
这正是容器里的形状，而且不需要 docker 就能跑。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src/social_archive"
MODULES = sorted(p.stem for p in PACKAGE.glob("*.py") if p.stem != "__init__")


@pytest.fixture(scope="module")
def detached(tmp_path_factory) -> Path:
    """把包复制到一个「周围什么都没有」的地方——镜像里就是这样。"""
    where = tmp_path_factory.mktemp("detached")
    shutil.copytree(PACKAGE, where / "social_archive")
    return where


def _env(detached: Path) -> dict[str, str]:
    """**数据目录指到临时盘，别的一概不给。**

    容器里 `/var/lib/social-archive` 是个可写的挂载点，本机没有——不指走的话
    这条判据红在「建不出目录」上，而那不是它要守的东西（守的是「仓不在了」）。
    指走的只有数据根，**代码/资源的路径一个都不给**：那正是要考的。
    """
    env = dict(os.environ)
    env["SOCIAL_ARCHIVE_DATA_ROOT"] = str(detached / "data")
    env.pop("PYTHONPATH", None)
    return env


def test_there_are_modules_to_check() -> None:
    """反空扫：一个模块都没数到的话，下面那条会白过。"""
    assert len(MODULES) >= 10, MODULES


def _import(detached: Path, statement: str) -> subprocess.CompletedProcess[str]:
    code = textwrap.dedent(f"""
        import sys, pathlib
        sys.path.insert(0, {str(detached)!r})
        import social_archive
        here = pathlib.Path(social_archive.__file__).resolve()
        # **先证明我们 import 的确实是那份挪走的副本。**
        # editable 安装会让 `import social_archive` 悄悄回到仓里，
        # 那样这条判据就在测一个它以为自己没在测的东西。
        assert str(here).startswith({str(detached)!r}), f"import 到的是仓里那份：{{here}}"
        {statement}
    """)
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, cwd="/", env=_env(detached), check=False)


def test_the_copy_is_really_what_gets_imported(detached: Path) -> None:
    """**先验夹具本身。** 这个仓栽过「夹具比原文干净就等于没测」五次以上。"""
    done = _import(detached, "print('ok')")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "ok" in done.stdout


@pytest.mark.parametrize("module", MODULES)
def test_every_module_imports_with_no_repo_around(detached: Path, module: str) -> None:
    done = _import(detached, f"import social_archive.{module}")
    assert done.returncode == 0, (
        f"`import social_archive.{module}` 在没有仓的环境里失败了——"
        f"镜像里就是这个环境，入口点会死在这里：\n"
        + (done.stderr or done.stdout)[-1500:])


def test_the_api_entrypoint_can_be_imported(detached: Path) -> None:
    """`social-archive-api` 起来时做的第一件事——它炸了就是生产全挂。"""
    done = _import(detached, "import social_archive.api; print(social_archive.api.app.title)")
    assert done.returncode == 0, (done.stderr or done.stdout)[-1500:]


def test_no_module_reads_a_repo_path_at_import_time(detached: Path) -> None:
    """**光能 import 还不够**：可能只是那句读文件恰好在函数里没被执行到。

    这里点名 `parents[2]`——它算出来的是「仓根」，而装好的包上面不是仓根。
    允许它出现在**兜底**语义里（`SECRET_FALLBACK_DIR` 那种、候选路径那种），
    但不许有人 import 时就去读它。
    """
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if "parents[2]" not in line or line.lstrip().startswith("#"):
                continue
            # 缩进的行在函数/类里，import 时不执行；顶层那种才是 import 时就跑
            if not line.startswith(" ") and "=" in line:
                offenders.append(f"{path.name}:{number} {line.strip()[:90]}")
    # 顶层出现是允许的（常量），但它必须只是**算个路径**，不能当场读。
    for entry in offenders:
        assert "read_text" not in entry and "open(" not in entry, (
            f"import 时就去读仓里的路径：{entry}——装进镜像之后那个路径不存在")
