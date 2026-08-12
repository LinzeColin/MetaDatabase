r"""`set -o pipefail` 下，一次正常的「没找到」不许把脚本打死（2026-08-10）。

## 它是怎么被发现的

给 Owner 做了个双击就能跑的「同步到 Obsidian.command」。第一次双击，
屏幕上同步明明成功了（文件修好、成分打出来了），最后却报

    没跑成（退出码 1）

**追这个 bug 我先改错了地方**：以为是 `[[ … ]] && printf` 在最后一项为假时
返回 1（那确实也是个隐患，但不是这次的原因）。改完再跑，还是 1。

第二次用 `bash -x` 追，才看见真因：

    ++ grep -rl '"bookmark"' … --include=*.md
    ++ wc -l
    + n=0
    （脚本到此终止）

**`grep` 找不到匹配时退出码是 1**，而脚本开着 `set -o pipefail`——
整条管道于是返回 1，`n=$(…)` 这个赋值失败，`set -e` 当场终止。

★ **更该记的是：我先前几次手跑也是这么退出的，而我没注意。**
因为数据那时已经同步完了，我只去数了库里的文件数，没看脚本的收尾。
这是「管道吃掉退出码」的变体：不是 `tail` 吃掉，是 `pipefail`
把一次**正常的「没找到」**变成了致命错误。

## 这条判据守什么

`set -o pipefail` 的 shell 脚本里，命令替换中出现的 `grep`
必须显式吃掉「没匹配」那一档（`|| true`）——否则空结果就是崩溃。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "scripts").glob("*.sh"))


def _pipefail_scripts() -> list[Path]:
    return [path for path in SCRIPTS
            if "pipefail" in path.read_text(encoding="utf-8")]


def test_there_is_something_to_check() -> None:
    """反空扫：一个开着 pipefail 的脚本都没有的话，下面那条会白过。"""
    found = _pipefail_scripts()
    assert found, "scripts/ 下没有开 pipefail 的 .sh——这条判据在空扫"


@pytest.mark.parametrize("path", _pipefail_scripts(), ids=lambda p: p.name)
def test_a_grep_that_finds_nothing_is_not_fatal(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    offenders: list[str] = []
    # **按行看，不按括号切。**（2026-08-10 第一版就栽在这儿）
    # `grep -oP '(?<=^FOO=)[0-9]+'` 里那个 `)` 会把 `\$\((.*?)\)` 提前截断，
    # 于是看不见后面的 `|| echo 18765`——deploy_to_production.sh 那两处
    # 本来就是安全的，却被报成违规。判据切错位置，这个仓当天记过第七次。
    for line in text.splitlines():
        if "grep" not in line or "$(" not in line:
            continue
        if "|| true" in line or "|| echo" in line or "grep -c" in line:
            continue
        offenders.append(line.strip()[:110])
    assert not offenders, (
        f"{path.name}：命令替换里的 grep 没有吃掉「没匹配」那一档 {offenders}——"
        "grep 找不到东西时退出码是 1，配上 pipefail + set -e，"
        "**一次正常的空结果就会把脚本打死**（同步其实成功了，却报「没跑成」）")


def test_the_double_click_wrapper_exists_and_is_runnable() -> None:
    """**他没有技术基础**——命令行不算「操作简单」。"""
    wrapper = ROOT / "scripts/同步到 Obsidian.command"
    assert wrapper.is_file(), (
        "没有双击就能跑的那个文件——Owner 说过他没有技术基础，"
        "让他去终端里敲命令不算「操作简单」")
    text = wrapper.read_text(encoding="utf-8")
    # **必须自包含。**（2026-08-10）
    # 上一版它指向 `_scratch/…` 里的脚本，而 `_scratch/` 按规矩就是放临时产物的
    # ——今天已经有另一棵 worktree 在半路整个消失过。
    # 他唯一能用的工具不该挂在一个随时会被回收的目录上。
    # **注释里提到 `_scratch` 是在解释为什么不能依赖它**——剔掉注释行再看。
    # 第一版没剔，被自己那句说明打红了（判据切错位置，当天第八次）。
    code_only = "\n".join(line for line in text.splitlines()
                          if not line.lstrip().startswith("#"))
    assert "_scratch" not in code_only, (
        "双击那个文件依赖 _scratch/ 里的脚本——那个目录随时可能被回收，"
        "他的按钮会突然失灵")
    assert "ssh" in text and "rsync" in text, "它不再自己完成同步了"
    # 合并进库之前要先修标题，否则重跑会和已经修好的那份撞成两个文件
    merge_at = text.index("rsync -a")
    assert "clean" in text[:merge_at] or "修好" in text[:merge_at], (
        "没有在合并进库之前修标题——重跑会把库弄成两份")
    # **失败时要说清楚**，不能双击完一闪而过什么都看不到。
    # 钉的是意图不是字面：上一版断言里有「退出码」三个字，
    # 而新版改成直接说具体原因（更好），字面就对不上了。
    assert "read -n 1" in text, (
        "双击那个文件跑完不挡窗口——一闪就没，他什么都看不到")
    failure_paths = re.findall(r"finish\s+\"[^\"]+\"\s+[1-9]", text)
    assert len(failure_paths) >= 3, (
        f"失败分支只有 {len(failure_paths)} 条带说明的——"
        "连不上服务器、取回失败、写库失败这些都该当场告诉他是哪一种")
