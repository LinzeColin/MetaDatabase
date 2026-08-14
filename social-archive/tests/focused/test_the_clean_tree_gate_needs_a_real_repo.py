r"""「工作树干净」这道门，在非 git 目录里必须**大声失败**（2026-08-14）。

## 它修的是什么

部署第 0 步原来是一行：

    [[ -z "$(git status --porcelain)" ]] || fail '本工作树有未提交改动。…'

**它只看 stdout。** 而 `git status --porcelain` 在非仓目录里
把错误写到 stderr、stdout 是空的、退出码 128 —— 实测：

    stdout=[]  长度=0  退出码=128

空字符串 → `-z` 成立 → **判「干净」并放行**。

## 这不是假想

rsync 把整棵树同步到生产，所以 **`/opt/social-archive/scripts/deploy_to_production.sh`
在生产机上也存在**；而 `/opt/social-archive` 是 rsync 的目标、**没有 `.git`**（实测）。
交接提示词让接手方「改代码之后必须跑 `deploy_to_production.sh`」——
他 ssh 进生产、看见脚本就在那儿、顺手一跑，这道本该拦住他的门会放行。

而这道门的意思是「部署的必须是**已入库的那一版**」：非仓里根本没有那一版，
所以正确答案是大声失败，不是安静通过。
（同族：空默认值吞掉「不知道」；「0 命中」先问命令能不能看见它。）

## 怎么测

不 mock：造一个**真的非 git 目录**，把脚本按原样放进去的 `scripts/` 下，
再放一个假的 `.venv/bin/python`（venv 那道自检排在第 0 步前面），
然后真跑一遍，读它印出来的话。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts/deploy_to_production.sh"


def _run_in_fake_tree(tmp_path: Path, make_repo: bool) -> subprocess.CompletedProcess:
    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    (tree / "deploy").mkdir(parents=True)
    (tree / "deploy" / "PRODUCTION_HOST").write_text("example-host\n", encoding="utf-8")
    # 第 0 步之前脚本还会读这几样；缺了会以别的错误先炸，测不到要测的那一支。
    (tree / "VERSION").write_text("0.0.0.0\n", encoding="utf-8")

    script = tree / "scripts" / "deploy_to_production.sh"
    script.write_text(DEPLOY.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o755)

    # venv 那道自检排在第 0 步前面，先让它过去（只要能执行、版本够就行）
    venv_bin = tree / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)

    if make_repo:
        env0 = dict(os.environ)
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            env0.pop(key, None)
        subprocess.run(["git", "init", "-q"], cwd=tree, env=env0, check=True)

    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    # `errors="replace"`：脚本在这个残缺夹具里可能吐出非 UTF-8 的字节
    # （实测 UnicodeDecodeError）。**读输出不许因此崩掉**——崩掉的话
    # 要测的那一支一个字都看不到，而失败原因会指向完全无关的地方。
    return subprocess.run(["bash", str(script)], cwd=tree, env=env,
                          capture_output=True, text=True, errors="replace", check=False)


def test_非git目录里必须挡下而不是放行(tmp_path: Path) -> None:
    done = _run_in_fake_tree(tmp_path, make_repo=False)
    text = done.stdout + done.stderr

    assert done.returncode != 0, (
        "在一个非 git 目录里，部署没有被挡下。\n"
        "  `git status --porcelain` 在这里 stdout 是空的（退出码 128），\n"
        "  只看 stdout 的写法会把它读成「工作树干净」。\n" + text)
    assert "不是一个 git 工作树" in text, (
        "挡是挡下了，但没说清是为什么——接手方会以为是别的毛病：\n" + text)
    # 出错要指得出去哪儿做对：回开发机的工作树
    assert "开发机" in text, "没告诉他该去哪儿跑：\n" + text


def test_真的是git仓时不许被这道新闸挡住(tmp_path: Path) -> None:
    """反方向。少了它，把闸写成「永远失败」也能让上面那条过，
    而那样整个部署就再也跑不起来了。"""
    done = _run_in_fake_tree(tmp_path, make_repo=True)
    text = done.stdout + done.stderr
    assert "不是一个 git 工作树" not in text, (
        "这是一个真的 git 仓，却被那道新闸挡住了：\n" + text)
