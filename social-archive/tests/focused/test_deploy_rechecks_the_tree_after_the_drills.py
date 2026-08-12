"""部署要在演练跑完之后再查一次进镜像的那些文件（2026-08-07）。

## 那天发生了什么

生产上摆了大约四十分钟一个**打不开连接面板**的扩展包。来路是：部署第 0 步的
「工作树干净」闸在最开头就过完了，而随后 `run_all_drills` 要跑五分钟，
**每个演练自己会重打一次包**。我在那五分钟里改了 manifest，坏的那份就这么被
打出来、同步上去了。

所以闸不能只在开头。但**范围不能是整棵树**——演练自己会写 `evidence/*.json`，
那不算脏；拿整棵树去查，这道闸每次都会误报，用不了几次就会被绕过去。
范围正好是**进镜像的那些输入**，而那份清单由 Dockerfile 现算
（`does_this_deploy_need_a_rebuild.py --list-inputs`），不在部署脚本里抄第二份。

## 这里为什么要测「在 bash 里」

`git status --porcelain -- $INPUTS` 靠**分词**把多行清单拆成多个 pathspec。
zsh 默认不给不带引号的变量分词——我第一次验这道闸就是在 zsh 里跑的，
反例没跳，差点据此断定「这道闸是空的」。部署脚本跑在 bash 里。
**要在收件人的环境里验，不是在我的终端里。**
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts/deploy_to_production.sh"
LISTER = "scripts/does_this_deploy_need_a_rebuild.py"

# 今天同一个坑踩了三次，症状都是「单独跑绿、pre-commit 里红」。cwd 压不过 GIT_DIR。
from social_archive.git_env import clean_git_env


def _inputs() -> list[str]:
    done = subprocess.run([".venv/bin/python", LISTER, "--list-inputs"],
                          cwd=ROOT, env=clean_git_env(),
                          capture_output=True, text=True, check=True)
    return [line for line in done.stdout.splitlines() if line.strip()]


def test_the_input_list_is_read_from_the_dockerfile() -> None:
    """清单必须现算。**写死一份就会和 Dockerfile 分家**，而分家那天没人会知道。"""
    inputs = _inputs()
    assert inputs, "清单是空的——**这不是「没有输入」**，是没数到"
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for item in inputs:
        assert item in dockerfile, f"{item} 不在 Dockerfile 里，这份清单是从哪来的？"
    assert {"apps", "src", "scripts"} <= set(inputs), inputs


def test_the_pathspec_sees_the_extension_and_ignores_the_evidence() -> None:
    """**在 bash 里**跑，因为分词是这道闸能不能成立的全部。

    用 `git ls-files` 而不是 `git status`：它是只读的，不用把工作树弄脏，
    而它答的正是同一个问题——「这份 pathspec 罩住了哪些文件」。
    """
    inputs = " ".join(_inputs())
    done = subprocess.run(
        ["bash", "-c", f"git ls-files -- {inputs}"],
        cwd=ROOT, env=clean_git_env(), capture_output=True, text=True, check=True)
    covered = set(done.stdout.splitlines())
    assert covered, (
        "这份 pathspec 一个文件都没罩住——要么分词没生效（zsh 不给不带引号的"
        "变量分词），要么环境里有别的仓的 GIT_DIR（pre-commit 会塞）")

    must = "apps/browser-extension/manifest.json"
    assert must in covered, (
        f"{must} 不在这道闸的范围里——**那天坏掉的就是它**")
    assert any(p.startswith("src/") for p in covered), covered
    leaked = [p for p in covered if p.startswith("evidence/")]
    assert not leaked, (
        f"evidence/ 被罩进来了：{leaked[:3]}——演练自己会写它，"
        "这道闸会每次误报，用不了几次就会被绕过去")


def test_the_deploy_actually_rechecks_after_the_drills() -> None:
    """**判据要有调用方。** 这道闸不接进部署就等于没有。"""
    text = DEPLOY.read_text(encoding="utf-8")
    assert "--list-inputs" in text, "部署没有取那份现算的清单"
    drills = text.index("run_all_drills.py")
    recheck = text.index("DIRTY_AFTER_DRILLS")
    sync = text.index('step "2) 同步源码"')
    assert drills < recheck < sync, (
        "这道闸的位置不对：必须**在演练之后、同步之前**——"
        "演练会重打包，同步会把包送上生产")
