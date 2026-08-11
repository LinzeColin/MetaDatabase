r"""「仓和生产一致」这道门，仓侧必须读 HEAD，不能读工作树（2026-08-12）。

## 这个洞的形状

部署脚本第 2 步把**工作树**同步到生产机，第 9 步的
`check_production_matches_the_repo.py` 原来也读**工作树**（`ROOT.rglob()` + `read_bytes()`）。
两边读的是同一个东西，于是：

    部署跑到一半，我改了工作树里的一个文件
      → 第 2 步已经把旧的送上去了，或者第 2 步把新的送上去了
      → 第 9 步拿工作树和生产比，**永远一致**

**它比的是自己和自己。** 一件东西证不了自己没被换过；
要比就得比一个它改不动的参照物——`HEAD`。

这一课本来已经学过一次（交付包那次：两个一样坏的东西比起来是一致的），
但当时只落在了扩展包上，这一步漏了。

## 这里测的是行为，不是措辞

不断言源码里有没有某个字符串——那种断言我切错过六次。
这里**真的**往工作树里放一个 HEAD 没有的文件，再问仓侧看不看得见。
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_production_matches_the_repo import _local_hashes  # noqa: E402


def _tracked(name: str) -> bool:
    done = subprocess.run(["git", "ls-files", "--error-unmatch", name],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    return done.returncode == 0


def test_it_reads_something_at_all() -> None:
    """正例。

    **反例必须配一个正例。** 一个恒空的 `_local_hashes()` 能让下面两条
    「看不见」全部通过——那不是守住了，那是瞎了。
    `git show HEAD:<path>` 从子目录调用会 fatal，正是这个形态：
    仓侧变成空字典，整个代码库被报成 only_on_production，每次部署都红。
    """
    assert len(_local_hashes()) > 100


def test_a_file_only_in_the_worktree_is_invisible() -> None:
    """部署途中新增的文件，仓侧不该看得见。"""
    probe = ROOT / "scripts/_head_only_probe_delete_me.py"
    assert not probe.exists(), "上一次跑漏删了，先清掉再说"
    probe.write_text("# 只在工作树里\n", encoding="utf-8")
    try:
        assert "scripts/_head_only_probe_delete_me.py" not in _local_hashes()
    finally:
        probe.unlink()


def test_an_uncommitted_edit_does_not_change_what_the_repo_side_sees() -> None:
    """改一个**已提交**文件而不提交，仓侧读到的必须还是 HEAD 那一版。

    备份用 `cp`，不用 `git checkout --`：后者会把同一个文件里**别人还没提交的
    真修复**一起吃掉（吃过一次）。
    """
    name = "scripts/read_production_sync_history.py"
    assert _tracked(name), f"{name} 没被跟踪，这条反例就落空了"
    target = ROOT / name
    backup = target.read_bytes()
    before = _local_hashes()[name]
    try:
        target.write_bytes(backup + b"\n# uncommitted\n")
        worktree_now = hashlib.sha256(target.read_bytes()).hexdigest()
        assert worktree_now != before, "改动没落盘，这条反例根本没生效"
        assert _local_hashes()[name] == before
    finally:
        target.write_bytes(backup)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
