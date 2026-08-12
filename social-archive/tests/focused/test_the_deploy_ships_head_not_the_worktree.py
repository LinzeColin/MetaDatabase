r"""部署第 2 步同步的必须是 HEAD 的快照，不是工作树（2026-08-12）。

## 为什么要有这条

第 0 步查完「工作树干净」之后，还要跑 1767 条测试（约 2.5 分钟）＋ 14 个演练
（约 5 分钟）才走到第 2 步——**每次部署都有 7–8 分钟的可写窗口**。
2026-08-12 我在这个窗口里改了**两次**工作树，两次都是 `.md`，
两次都是自己赶在 rsync 之前发现并挪走的：**靠的是记性，不是机制**。

早上给第 9 步加的「仓侧读 HEAD」挡不住这一类：它的 `COMPARED` 只看
`scripts/ src/ apps/` 下的 `.py .sh .js .css .html .json`——**`.md` 不在里面**。
一道防线挡不住立它的人当天犯的同一个错，就是没挡住。

所以第 2 步改成从 `git archive HEAD` 的快照同步。
这条判据钉的就是那个性质：**改了工作树，快照里看不见。**

## 这里测的是行为，不是措辞

不断言脚本里有没有 `git archive` 这几个字——那种断言我今天切错过好几次。
这里真的改一个已跟踪文件、真的取一次快照、再读快照里那个文件。
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.git_env import clean_git_env  # noqa: E402


def _git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=cwd or ROOT, env=clean_git_env(),
                          capture_output=True, text=True, check=True)
    return done.stdout


def _snapshot_bytes(name: str) -> bytes | None:
    """按部署第 2 步的走法取一次快照，读出里面那个文件。"""
    top = _git("rev-parse", "--show-toplevel").strip()
    prefix = _git("rev-parse", "--show-prefix").strip().rstrip("/")
    done = subprocess.run(["git", "-C", top, "archive", f"HEAD:{prefix}"],
                          env=clean_git_env(), capture_output=True, check=True)
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "snap.tar"
        tar_path.write_bytes(done.stdout)
        with tarfile.open(tar_path) as tar:
            try:
                member = tar.extractfile(name)
            except KeyError:
                return None
            return member.read() if member else None


def test_the_snapshot_has_real_content() -> None:
    """正例。

    **反例必须配正例**：一个恒空的快照能让下面那条「看不见改动」通过，
    那不是守住了，那是瞎了。而空快照是真会发生的——在子目录里跑
    `git archive HEAD:<子目录>` 会 `fatal: current working directory is untracked`，
    exit=128、0 字节（今天实测）。所以这条先确认快照真有东西。
    """
    data = _snapshot_bytes("scripts/deploy_to_production.sh")
    assert data and len(data) > 1000, "快照里没有部署脚本——多半是 0 字节的空快照"


def test_an_uncommitted_edit_never_reaches_the_snapshot() -> None:
    """改了工作树，快照里必须看不见。

    备份用 `cp`，不用 `git checkout --`：后者会把同一个文件里别人还没提交的
    真修复一起吃掉（吃过一次）。
    """
    name = "scripts/read_production_sync_history.py"
    target = ROOT / name
    backup = target.read_bytes()
    marker = b"\n# uncommitted-marker-that-must-not-ship\n"
    try:
        target.write_bytes(backup + marker)
        assert marker in target.read_bytes(), "改动没落盘，这条反例根本没生效"
        shipped = _snapshot_bytes(name)
        assert shipped is not None, f"快照里没有 {name}"
        assert marker not in shipped, "**工作树的改动混进了快照**——第 2 步还是在送工作树"
    finally:
        target.write_bytes(backup)


def test_an_untracked_file_never_reaches_the_snapshot() -> None:
    """部署途中新建的文件也不许进快照——**包括 `.md`**。

    我两次犯的都是这一种，而第 9 步那道门恰恰不看 `.md`。
    """
    probe = ROOT / "scripts/_snapshot_probe_delete_me.md"
    assert not probe.exists(), "上一次跑漏删了，先清掉"
    probe.write_text("部署途中新建的说明\n", encoding="utf-8")
    try:
        assert _snapshot_bytes("scripts/_snapshot_probe_delete_me.md") is None
    finally:
        probe.unlink()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
