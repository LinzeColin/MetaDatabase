"""那道「起 git 必须自己决定环境」的门，喂它坏片段必须变红（2026-08-07）。

2026-08-07 一天之内踩了三次同一个坑：git 钩子把 `GIT_DIR` 塞进环境，
子进程于是去问**那个**仓而不是 `cwd=` 指的这个。症状都是
**单独跑是绿的，pre-commit 里红**。

而最坏的一种不是红，是**静悄悄读了另一个仓**——那时候数是出得来的，只是错的。
`scan_plaintext_credentials.py` 正是这一种：它靠 `git ls-files` 决定扫哪些文件，
环境脏了它会去扫别的仓，然后报「0 处命中」。这道门当场把它抓出来了。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_git_calls_cannot_be_hijacked_by_hooks.py"

_spec = importlib.util.spec_from_file_location("_git_env_gate", SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_git_env_gate"] = _module
_spec.loader.exec_module(_module)
offenders = _module.offenders


def test_a_bare_git_call_is_caught() -> None:
    source = 'import subprocess\nsubprocess.run(["git", "status"], cwd="/x")\n'
    assert offenders(source, "x.py") == ["x.py:2"], offenders(source, "x.py")


def test_a_cleaned_call_passes() -> None:
    """**正例必须是绿的。** 一条永远喊红的门和永远说 PASS 的一样没用。"""
    source = ('import subprocess\n'
              'subprocess.run(["git", "status"], cwd="/x", env=clean_git_env())\n')
    assert offenders(source, "x.py") == []


def test_an_explicit_inherit_passes() -> None:
    """`env=None` 放行——**有一份判据故意带着脏环境跑**，它测的正是漏没漏这一步。

    把「故意」和「忘了」分开的办法是让它写出来，而不是让这道门去猜。
    """
    source = 'import subprocess\nsubprocess.run(["git", "log"], env=None)\n'
    assert offenders(source, "x.py") == []


def test_git_through_a_shell_is_caught() -> None:
    """`bash -c "git ..."` 一样会继承 GIT_DIR——**换个壳不换性质**。"""
    for argv in ('["bash", "-c", "git ls-files -- src"]',
                 '["sh", "-c", f"git ls-files -- {paths}"]',
                 '"git rev-parse HEAD"'):
        source = f"import subprocess\nsubprocess.run({argv}, shell=True)\n"
        assert offenders(source, "x.py") == ["x.py:2"], argv


def test_a_non_git_call_is_left_alone() -> None:
    """**别把不相干的调用也拖下水**，那样这道门会被当成噪音绕过去。"""
    source = ('import subprocess\n'
              'subprocess.run(["docker", "ps"])\n'
              'subprocess.run(["bash", "-c", "ls -l"])\n')
    assert offenders(source, "x.py") == []


def test_the_gate_is_wired_into_the_release_gate() -> None:
    """**判据要有调用方。** 不挂进发布门就只在有人想起来时才生效。"""
    text = (ROOT / "scripts/final_verify.py").read_text(encoding="utf-8")
    assert "check_git_calls_cannot_be_hijacked_by_hooks.py" in text


def test_the_gate_refuses_to_pass_on_an_empty_scan() -> None:
    """**数到 0 处 git 调用不是通过，是扫描坏了。**

    这个仓在「空扫被读成绿」上栽过很多次，所以这道门自己带了个下限。
    """
    source = (SCRIPT).read_text(encoding="utf-8")
    assert "git_calls < 5" in source, "这道门没有防空扫的下限"
    assert "在空扫" in source
