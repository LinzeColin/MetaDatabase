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
