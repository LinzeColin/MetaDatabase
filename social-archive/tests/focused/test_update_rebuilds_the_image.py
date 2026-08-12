"""更新一台已装好的机器时，镜像必须被重建（v0.0.0.7 / T18 前置）。

## 这个洞是查部署面时撞到的

生产的 Core 由 `social-archive.service` 管着，而它的 ExecStart 是：

    /usr/bin/docker compose up -d core-api core-worker

**没有 `--build`。** `scripts/start.sh` 同样没有（它只 `--force-recreate`）。
全仓唯一会 build 的是 `install.sh`，而那是**首次安装**才跑的。

于是「拉新代码 → systemctl restart」这条最自然的更新路径，
容器会用**旧镜像**重建，代码改动一个字都没进去——
而服务起来了、`/health` 200、日志没有异常。

对本项目具体意味着：C-T00-01 的根因修复在 `sidecars/cli-tools/Dockerfile` 里，
不重建镜像，CLI Sidecar 依旧读不到自己的密钥，界面依旧永远「同步中」。
Owner 会得出「这个修复没用」的结论，而其实它根本没被装上。

## 判据守什么

  · 存在一条会重建镜像的更新路径
  · 运维手册明说 `systemctl restart` 不做这件事
  · 那条路径在工作树不干净时拒绝继续
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPDATE = ROOT / "scripts/update.sh"
MANUAL = ROOT / "docs/06_运维手册.md"
UNIT = ROOT / "deploy/systemd/social-archive.service"


def test_the_systemd_unit_really_does_not_rebuild() -> None:
    """先把前提证实了，否则下面几条就是在防一个不存在的问题。"""
    text = UNIT.read_text(encoding="utf-8")
    exec_start = next(line for line in text.splitlines() if line.startswith("ExecStart="))
    assert "docker compose up" in exec_start
    assert "--build" not in exec_start, (
        "unit 现在会 build 了——那这条判据要改成守 unit，而不是守 update.sh"
    )


def test_an_update_path_exists_and_rebuilds() -> None:
    assert UPDATE.is_file(), "没有任何一条会重建镜像的更新路径"
    text = UPDATE.read_text(encoding="utf-8")
    assert re.search(r"docker compose build[^\n]*core-api[^\n]*core-worker[^\n]*cli-tools", text), (
        "更新脚本没有重建三个镜像 —— cli-tools 漏掉的话 C-T00-01 的修复不会生效"
    )
    build_at = text.index("docker compose build")
    recreate_at = max(text.index("systemctl restart social-archive.service"),
                      text.index("docker compose up -d --force-recreate"))
    assert build_at < recreate_at, "先重建容器再 build，等于这次更新还是旧镜像"


def test_it_refuses_on_a_dirty_tree_but_still_runs_without_git() -> None:
    """两件事都要：脏工作树要拦，**非 git 目录不能被拦死**。

    实测 2026-08-04：生产的 /opt/social-archive **不是 git 检出**
    （`git rev-parse` 报 not a git repository）。第一版无条件要求工作树干净，
    于是它在唯一真正需要用它的那台机器上直接拒绝运行——
    判据全绿、本机能跑，**只是跑不了生产**。
    """
    text = UPDATE.read_text(encoding="utf-8")
    assert "git status --porcelain" in text
    assert "工作树不干净" in text
    assert "git rev-parse --git-dir" in text, "没有先判断这是不是 git 检出"
    assert "跳过干净度检查" in text, "非 git 目录会被拦死，而生产正是非 git"


def test_the_script_is_valid_bash() -> None:
    result = subprocess.run(["bash", "-n", str(UPDATE)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_the_manual_says_restart_is_not_enough() -> None:
    """光有脚本不够——照着旧习惯敲 restart 的人得在手册里被拦一下。"""
    manual = MANUAL.read_text(encoding="utf-8")
    assert "不会重建镜像" in manual
    assert "scripts/update.sh" in manual
    assert "backup.sh" in manual, "更新前没提示先取快照，回滚就没有可恢复的东西"
