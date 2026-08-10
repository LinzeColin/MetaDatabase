r"""换生产机器时，他桌面上那个双击文件也得跟着换（2026-08-10）。

桌面那份**必须自包含**——不能依赖仓里的 `deploy/PRODUCTION_HOST`，
因为 `_scratch/` 里的工作树随时会被回收（今天就有一棵在部署跑到一半时整棵消失）。
自包含的代价是主机名在里面是字面值，换机器不会自动跟上。

不跟上的后果不是报错，是**静默连回旧机器**：真源改了、生产切了，
他一双击还是老地方，而屏幕上什么异常都没有。

`scripts/refresh_desktop_launcher.py` 就是那一步；这条判据钉它真的会跟着真源变、
`--check` 真的会在漂开时红。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/refresh_desktop_launcher.py"


def _run(home: Path, host: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["SOCIAL_ARCHIVE_DEPLOY_HOST"] = host
    (home / "Desktop").mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=env, check=False)


def test_it_writes_both_files_with_the_current_host(tmp_path: Path) -> None:
    done = _run(tmp_path, "some-other-box")
    assert done.returncode == 0, done.stdout + done.stderr
    main = tmp_path / "Desktop/同步到 Obsidian.command"
    fav = tmp_path / "Desktop/只补收藏到 Obsidian.command"
    assert main.is_file() and fav.is_file()
    text = main.read_text(encoding="utf-8")
    assert 'HOST="${SOCIAL_ARCHIVE_HOST:-some-other-box}"' in text, (
        "桌面那份没跟上真源里的主机名——换机器后他会静默连回旧的那台")
    assert os.access(main, os.X_OK), "双击文件没有可执行位"


def test_check_goes_red_when_the_host_drifts(tmp_path: Path) -> None:
    assert _run(tmp_path, "box-a").returncode == 0
    drifted = _run(tmp_path, "box-b", "--check")
    assert drifted.returncode == 1, drifted.stdout
    assert "不一致" in drifted.stdout, drifted.stdout
    assert "refresh_desktop_launcher.py" in drifted.stdout, (
        "报了不一致却没给出怎么修——这个仓栽过「错误提示指向不存在的出口」")


def test_check_is_green_right_after_a_refresh(tmp_path: Path) -> None:
    assert _run(tmp_path, "box-a").returncode == 0
    done = _run(tmp_path, "box-a", "--check")
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_refresher_the_command_file_points_at_really_exists() -> None:
    """`.command` 的注释里写着换机器时跑哪个脚本——它得真的在。"""
    text = (ROOT / "scripts/同步到 Obsidian.command").read_text(encoding="utf-8")
    assert "refresh_desktop_launcher.py" in text
    assert SCRIPT.is_file(), "注释指向一个不存在的脚本"


def test_the_rendered_file_is_valid_bash(tmp_path: Path) -> None:
    """**渲染出来的那份要能跑**，不是「模板看着对」。"""
    assert _run(tmp_path, "box-a").returncode == 0
    for name in ("同步到 Obsidian.command", "只补收藏到 Obsidian.command"):
        done = subprocess.run(["bash", "-n", str(tmp_path / "Desktop" / name)],
                              capture_output=True, text=True, check=False)
        assert done.returncode == 0, f"{name} 语法不过：{done.stderr}"
