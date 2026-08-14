r"""决定「成还是败」的那一步，不许接管道（2026-08-10）。

## 这个仓栽过三次，形状一模一样

1. `pytest -q 2>&1 | tail -3 && git add … && git commit`
   ——`&&` 看的是 `tail` 的退出码，于是我**提交了一个红的判据**。
2. 部署通知报 `exit 0`，而脚本自己报「第 2 步未过」；
   zsh 里 `${PIPESTATUS[0]}` 还恒为空，追起来更绕。
3. **最坏的一次是这次找出来的**：

       ssh "$HOST" "cd … && docker compose build core-api 2>&1 | tail -3" || fail '构建失败…'

   管道写在 ssh 的**引号里**，所以 ssh 的退出码就是远端 `tail` 的——恒 0。
   主机构建失败时 `|| fail` 永不触发，部署接着往下走、
   用**旧镜像** `docker compose up -d`，最后打印「部署成功」。
   他会看到一次「成功」的部署，而改的东西一样没上去。

## 判据守什么

`scripts/*.sh` 里，凡是用 `|| fail` / `|| exit` / `&&` 决定后续走向的那一行，
它前面那截不许是「管道到 tail/head」。要看输出就先落盘、判完退出码再 `tail`。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "scripts").glob("*.sh")) + [ROOT / "scripts/同步到 Obsidian.command"]
DECIDERS = re.compile(r"\|\|\s*(fail|exit|die|abort)\b|&&\s*(git|exit)\b")
SWALLOWS = re.compile(r"\|\s*(tail|head)\b")


def test_there_is_something_to_check() -> None:
    """反空扫：一个决定成败的行都没数到的话，下面那条会白过。"""
    total = sum(len(DECIDERS.findall(p.read_text(encoding="utf-8")))
                for p in SCRIPTS if p.exists())
    assert total >= 5, f"只数到 {total} 处「靠退出码决定走向」——判据在空扫"


@pytest.mark.parametrize("path", [p for p in SCRIPTS if p.exists()], ids=lambda p: p.name)
def test_no_decision_reads_a_pipes_exit_code(path: Path) -> None:
    offenders: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        found = DECIDERS.search(line)
        if not found:
            continue
        # **只看判定符号左边那一截。**（右边是失败时才跑的收尾，接管道无所谓）
        before = line[: found.start()]
        if SWALLOWS.search(before):
            offenders.append(f"{number}: {line.strip()[:120]}")
    assert not offenders, (
        f"{path.name} 里有「拿管道的退出码决定成败」：\n  " + "\n  ".join(offenders)
        + "\n管道的退出码是**最后一个**命令的（`tail` 几乎永远成功），"
          "所以失败会被读成成功。先落盘、判完退出码再 tail。")
