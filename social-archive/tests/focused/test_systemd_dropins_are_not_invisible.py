"""systemd 的 drop-in 也要被漂移检查看见（2026-08-10）。

## 撞见的事

部署第 3.5 步「systemd 单元有没有漂」原来只 glob `*.service` 和 `*.timer`。
而 systemd 还认 `<unit>.d/*.conf`，**drop-in 能改 `ExecStart`**——
也就是能改这个服务到底跑什么。

他生产上就有一个：

    /etc/systemd/system/social-archive-backup.service.d/20-prune-r2-replicas.conf
    ExecStart=…/prune_r2_backup_replicas.py --apply

**任何仓里都没有这个文件**，而它往备份服务里挂了一条对 R2 备份做真删除的任务，
三天里跑过 6 次。这一步照报「所有 systemd 单元与仓里一致」。

那个删除本身是对的（Owner 2026-08-10 定「R2 只留 3 天」；脚本先核 OCI 上同 key
同大小才删、最新一批永不删、不碰 `primary-objects/`）。
**问题不是它做了什么，是它从版本控制之外做的**——主机一旦重建，
这条会无声消失，而 R2 会重新涨回去。

现在 `.conf` 收进 `deploy/systemd/<unit>.d/`，第 3.5 步也盯着它。

## 这里钉三件事

1. 那个 glob 必须包含 drop-in。
2. drop-in 的目标路径要**连它的 `.d` 目录一起**——
   第一版我写的 case 模式配不上相对路径，目标算成了
   `/etc/systemd/system/20-prune-r2-replicas.conf`（一个不存在的位置），
   于是那道门会永远在比一个不存在的文件。**把 glob 打印出来看一眼才露的。**
3. 仓里每一个 unit / drop-in 都要真的落在这个 glob 里——
   加了新文件而 glob 没跟上，就又回到「看不见」。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts/deploy_to_production.sh"
UNITS = ROOT / "deploy/systemd"

pytestmark = pytest.mark.skipif(not DEPLOY.is_file(), reason="部署脚本不在")


def _glob_line() -> str:
    text = DEPLOY.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.lstrip().startswith("for unit in deploy/systemd/"))
    return line


def test_the_drift_check_globs_dropins_too() -> None:
    line = _glob_line()
    assert "*.d/*.conf" in line, (
        f"第 3.5 步的 glob 里没有 drop-in：{line.strip()}——"
        "drop-in 能改 ExecStart，看不见它就等于看不见这个服务在跑什么")
    for wanted in ("*.service", "*.timer"):
        assert wanted in line, f"原来收的 {wanted} 被漏掉了：{line.strip()}"


def test_the_dropin_target_path_keeps_its_dot_d_directory() -> None:
    """**别只取 basename。** 那会指到 /etc/systemd/system/ 下一个不存在的位置。"""
    text = DEPLOY.read_text(encoding="utf-8")
    branch = re.search(r"^\s*deploy/systemd/\*\.d/\*\)\s*name=(.+)$", text, re.M)
    assert branch, "找不到 drop-in 那条 case 分支（或者它的模式又写成了配不上的形式）"
    body = branch.group(1)
    assert "dirname" in body and "basename" in body, (
        f"drop-in 的目标路径没有带上 .d 目录：{body}")


def test_every_unit_and_dropin_in_the_repo_is_covered_by_that_glob() -> None:
    """仓里加了新文件而 glob 没跟上，就又回到「看不见」。"""
    if not UNITS.is_dir():
        pytest.skip("deploy/systemd 不在")
    line = _glob_line()
    # **末尾那个 `;` 是 shell 的，不是 glob 的。** 不剥掉的话
    # `deploy/systemd/*.d/*.conf;` 谁也配不上，这条判据会红在自己的解析上，
    # 而报出来的却是「产品有缺口」——今天就先这么红了一次。
    patterns = [p.rstrip(";&|") for p in line.split() if p.startswith("deploy/systemd/")]
    assert patterns, line
    assert all(not p.endswith(";") for p in patterns), patterns
    uncovered: list[str] = []
    for path in sorted(UNITS.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if not any(Path(rel).match(pattern) for pattern in patterns):
            uncovered.append(rel)
    assert uncovered == [], (
        f"这些文件在仓里，却不在第 3.5 步的 glob 里：{uncovered}——"
        "它们改了生产也不会被发现")


def test_the_prune_dropin_is_actually_in_the_repo_now() -> None:
    """**这条判据的由来**：那个删除任务此前只存在于主机上。"""
    conf = UNITS / "social-archive-backup.service.d/20-prune-r2-replicas.conf"
    assert conf.is_file(), (
        "那个 drop-in 又不在仓里了——它往备份服务里挂的是 `--apply` 的真删除，"
        "只活在主机上意味着主机重建时它会无声消失")
    body = conf.read_text(encoding="utf-8")
    assert "prune_r2_backup_replicas.py" in body and "--apply" in body, body[:200]
    assert (ROOT / "scripts/prune_r2_backup_replicas.py").is_file(), (
        "drop-in 指向的脚本不在仓里——那它在主机上跑的是哪一份，没人说得清")
