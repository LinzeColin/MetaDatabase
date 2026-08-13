r"""「生产是哪台机器」只准有一个真源（2026-08-10）。

## 从哪来

`social-archive-api.linzezhang.com` 背后其实是两台机器：他打到的那台
（95.82G / 0.0.0.25）和我部署的那台（38G / 0.0.0.27）。要换过去时我才发现，
`linze-ovh` 这个名字**写死在 16 个文件、21 处**，其中只有 9 处能用环境变量覆盖。

换机器于是不是改一个配置，而是改十几处——**漏掉的那几处会静默地继续连旧机器**，
没有任何东西会报错。这正是这个仓反复吃亏的那一类：同一件事两份词典必然漂开。

## 钉什么

`scripts/` 下的可执行代码里不许再出现写死的主机名；默认值一律来自
`deploy/PRODUCTION_HOST`（临时覆盖用 `SOCIAL_ARCHIVE_DEPLOY_HOST`）。
注释和文档字符串里可以出现（它们在讲历史，改了反而变成假话）。

## ★ 2026-08-13 补上文档那一半

上面这条只管 `scripts/`。而 `docs/06_运维手册.md` 的**回滚命令**里一直写着
`ssh linze-ovh`——**那台机器已经连不上了**（实测 139.99.61.6 超时）。
半夜要回滚的人照着敲，会挂在超时上，还以为是自己网络的问题。

所以再钉一条：**`docs/` 里可以复制粘贴的命令块（```bash / ```sh）
不许出现写死的主机名**。散文里讲历史照旧允许——
风险在他会照着敲的那几行，不在解释来龙去脉的句子里。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "deploy/PRODUCTION_HOST"


def test_the_single_source_exists_and_is_one_line() -> None:
    assert SOURCE.is_file(), "deploy/PRODUCTION_HOST 不在——生产是哪台没有真源"
    name = SOURCE.read_text(encoding="utf-8").strip()
    assert name and "\n" not in name, f"真源里不是一行主机名：{name!r}"


def test_the_helper_reads_it() -> None:
    done = subprocess.run([sys.executable, str(ROOT / "scripts/production_host.py")],
                          capture_output=True, text=True, check=False,
                          env={"PATH": "/usr/bin:/bin"})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == SOURCE.read_text(encoding="utf-8").strip()


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """剔掉注释与文档字符串——它们在讲历史，写着旧名字是对的。"""
    out, in_doc = [], False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.count('"""') == 1 or stripped.count("r\"\"\"") == 1:
            in_doc = not in_doc
            continue
        if in_doc or stripped.startswith("#"):
            continue
        out.append((number, line))
    return out


@pytest.mark.parametrize(
    "path",
    [p for p in sorted((ROOT / "scripts").iterdir())
     if p.suffix in {".py", ".sh"} and p.name not in {"production_host.py"}],
    ids=lambda p: p.name)
def test_no_script_hardcodes_the_host(path: Path) -> None:
    name = SOURCE.read_text(encoding="utf-8").strip()
    offenders = [f"{number}: {line.strip()[:100]}"
                 for number, line in _code_lines(path)
                 if re.search(rf"\b{re.escape(name)}\b", line)
                 and "PRODUCTION_HOST" not in line]
    assert not offenders, (
        f"{path.name} 里写死了主机名：\n  " + "\n  ".join(offenders)
        + f"\n默认值要走 deploy/PRODUCTION_HOST（py 用 production_host.deploy_host()）。"
          "写死的话，换机器时漏掉这一处就会静默连回旧机器。")


# ── 文档里那些他会照着敲的命令 ──────────────────────────────────────────

DOCS = ROOT / "docs"
_FENCE = re.compile(r"```(?:bash|sh|shell)\n(.*?)```", re.S)
# **这里要认所有的机器别名，不只是当前那台。**
# 上面那条判据只挡当前主机名（为的是"换机器只改一处"）；文档这一侧的风险
# 反过来——写着一台**已经不存在**的机器，照着敲的人挂在超时上，
# 而当前主机名的判据一个字都不会说。
HOSTNAME_IN_CODE = re.compile(r"\blinze-[a-z0-9]+\b")


def _command_blocks() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for path in sorted(DOCS.rglob("*.md")):
        for block in _FENCE.findall(path.read_text(encoding="utf-8")):
            out.append((path, block))
    return out


def test_the_scan_finds_command_blocks() -> None:
    """**先证明这把尺子量得到东西**——围栏写法一变就会一块都扫不到。"""
    blocks = _command_blocks()
    assert len(blocks) >= 5, f"只扫到 {len(blocks)} 个命令块，围栏正则多半没匹配上"
    assert any("ssh" in b for _p, b in blocks), "扫到的块里一个 ssh 都没有，取错地方了"


def test_没有文档让他去连一台写死的机器() -> None:
    """`docs/` 里可复制的命令块不许写死主机名。

    2026-08-13 实测：`linze-ovh`（139.99.61.6）已经连不上，
    而运维手册的回滚命令还指着它。
    """
    bad = [(path.name, block.strip()[:70])
           for path, block in _command_blocks() if HOSTNAME_IN_CODE.search(block)]
    assert not bad, (
        f"这些命令块里写死了主机名，照着敲会连到一台可能已经不存在的机器：{bad}\n"
        f"改成从真源取：`H=\"$(cat deploy/PRODUCTION_HOST)\"` 再用 `ssh \"$H\"`。")
