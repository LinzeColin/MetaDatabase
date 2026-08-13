r"""文档里的 ssh 命令，要读**生产的**状态，不是我这台机器的（2026-08-14）。

## 一次会在最坏的时候发作的漏

`docs/06_运维手册.md` 的回滚那一行原来是：

    ssh "$H" "cd /opt/social-archive && docker tag social-archive/core:rollback \
      social-archive/core:$(cat VERSION 2>/dev/null || echo 0.0.0.70) && docker compose up -d …"

**双引号里的 `$(...)` 在敲命令的那台机器上展开**，读的是**开发机仓里**的 VERSION。
而人会来回滚，通常正是因为刚发的新版有问题——**本机那个版本号比生产新**。

实测（同一条 ssh，只差引号）：

    双引号里 $(hostname -s) → Mac
    单引号里 $(hostname -s) → vps-bab7f9dc

紧跟在那条命令后面的注解自己也写着「要填**当前跑着的那一版**」、
「**写错版本号不会报错**，只会把标签打到一个不存在的名字上」——
**命令和注解互相矛盾，而会被复制粘贴的是命令。**
后果不是报错，是**你以为回滚了、其实没有**，在事故正中间。

那个 `|| echo 0.0.0.70` 的兜底也一起去掉了：它已经落后十几版。

## 口径

只管**运维手册里的 ssh 命令**。别处的 ssh（部署脚本自己发的）由别的判据管；
这里钉的是「给人照着敲的那几行」。写出来免得被当成覆盖了全部。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "docs/06_运维手册.md"

def _command_lines() -> list[str]:
    """只取 ```bash 围栏里的命令行。

    **必须切出来。** 第一版整篇扫，结果被我自己写在旁边的说明文字打中——
    那段解释里逐字引了 `|| echo 0.0.0.70`（在说"这个兜底已经去掉了"），
    判据当场把它当成还在的命令报了出来。
    今天同一形状犯了四次：**我写来解释修复的话，把判据本身废掉。**
    """
    lines, inside = [], False
    for raw in MANUAL.read_text(encoding="utf-8").splitlines():
        if raw.strip().startswith("```"):
            inside = raw.strip().startswith("```bash")
            continue
        if inside:
            lines.append(raw.strip())
    return lines


def _ssh_lines() -> list[str]:
    return [line for line in _command_lines() if line.startswith("ssh ")]


def test_手册里有ssh命令可查() -> None:
    """**先确认这道门有东西可看。** 手册改写之后一条 ssh 都扫不到时，
    它会安静地全绿——那种绿和"没问题"长得一样。"""
    lines = _ssh_lines()
    assert lines, (
        "运维手册里一条 ssh 命令都没扫到。写法变了就把这里一起改——"
        "否则这道判据会对着空集合永远绿。")


def test_问生产状态的取值必须在生产机上展开() -> None:
    problems = []
    for line in _ssh_lines():
        # 取 ssh 之后被引号包起来的那一段远端脚本
        body = re.search(r"ssh\s+[^'\"]*(['\"])(.*)\1\s*$", line)
        if not body:
            continue
        quote, remote = body.group(1), body.group(2)
        # **要抓的是"会在本机展开"，不是"出现了某个命令名"。**
        # 第一版把 `docker image inspect` 也列成必须远端，于是
        # `ssh "$H" "sudo docker image inspect …"` 被报了出来——
        # 那一行里根本没有 `$(`，双引号完全无害。**假阳会让人去改没坏的东西。**
        if quote != '"':
            continue
        for expansion in re.findall(r"\$\([^)]*\)|`[^`]*`", remote):
            problems.append(
                f"  {line}\n"
                f"    ↑ `{expansion}` 写在**双引号**里 → 在敲命令那台机器上展开，"
                "读到的是开发机的状态，不是生产的。")
    assert not problems, (
        "这些 ssh 命令问的是生产的状态，却会在本机取值：\n"
        + "\n".join(problems)
        + "\n\n  实测：同一条 ssh，双引号里 $(hostname -s) 出来是 Mac，"
          "单引号里出来是 vps-bab7f9dc。\n"
          "  改成单引号，让它在生产机上执行。")


def test_回滚命令不许写死一个会过期的版本号兜底() -> None:
    """`|| echo 0.0.0.70` 这种兜底比没有更坏。

    **打错标签不会报错**，只会安静地打到一个不存在的名字上——
    人以为回滚了，其实没有。宁可让它当场因为读不到 VERSION 而失败。
    """
    # 只看命令行——说明文字里可以（而且应该）引用这个旧写法来解释它为什么被去掉
    stale = re.findall(r"\|\|\s*echo\s+(\d+\.\d+\.\d+\.\d+)", "\n".join(_command_lines()))
    assert not stale, (
        f"手册里有写死的版本号兜底：{stale}\n"
        "  版本号每次发布都变，这种兜底必然过期；而打错标签是**静默**失败。")
