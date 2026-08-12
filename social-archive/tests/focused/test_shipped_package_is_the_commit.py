"""那条「发出去的包 = 入了库的代码」判据，喂它坏形状必须变红（2026-08-07）。

当天真的发生过：生产上摆了约四十分钟一个 `host_permissions` 缺了后端域名的
扩展包，插件够不着 API，连接面板显示「读不到可连接的来源」，一颗按钮都没有。
部署第 8 步没拦住——它比的是「服务器上的 zip」对「我这台机器上的 zip」，
**两个一样坏的东西比起来是一致的**。

所以这里逐个证明新判据会红，包括**它自己第一版栽的那一跤**：git 路径少了
仓内前缀，27 个文件全被跳过，打出「0 个不同」——差点被读成通过。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_the_shipped_package_is_the_committed_code.py"

_spec = importlib.util.spec_from_file_location("_shipped_package_check", SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_shipped_package_check"] = _module
_spec.loader.exec_module(_module)
compare = _module.compare


COMMITTED = {"manifest.json": b'{"version": "0.0.0.22"}',
             "bridge.js": b"// bridge\n",
             "connect-frame.js": b"// frame\n"}


def _head(rel: str) -> bytes | None:
    return COMMITTED.get(rel)


def test_an_identical_package_passes() -> None:
    """**正例必须是绿的。** 一条永远喊红的判据和永远说 PASS 的一样没用。"""
    problems, measured = compare(dict(COMMITTED), _head)
    assert problems == [], problems
    assert measured["identical_to_head"] == 3


def test_a_tampered_file_is_caught() -> None:
    """当天那一份：manifest 少了后端域名，其余一个字节没差。"""
    package = dict(COMMITTED)
    package["manifest.json"] = b'{"version": "0.0.0.22", "host_permissions": []}'
    problems, measured = compare(package, _head)
    assert any("不是同一份" in p for p in problems), problems
    assert any("manifest.json" in p for p in problems), problems
    assert measured["differs_from_head"] == 1


def test_an_extra_file_is_caught() -> None:
    """包里多出 HEAD 里没有的东西，说明它不是从这个提交打出来的。"""
    package = dict(COMMITTED)
    package["leftover-from-my-machine.js"] = b"// ?\n"
    problems, _ = compare(package, _head)
    assert any("HEAD 里不存在" in p for p in problems), problems


def test_an_empty_scan_is_a_failure_not_a_pass() -> None:
    """**这条判据自己第一版就栽在这儿。**

    git 路径少了仓内前缀 → 每个 `git show` 都失败 → 全被跳过 →
    打出「0 个逐字节一致，0 个不同」。那句话看着像通过，其实是
    **什么都没比**。空默认值吞掉「不知道」，这个仓在这上面栽过很多次。
    """
    problems, measured = compare({}, _head)
    assert any("一个文件都没比到" in p for p in problems), problems
    assert measured["identical_to_head"] == 0

    # 更阴的一种：包里有文件，但 HEAD 那侧一个都读不出来。
    problems, _ = compare(dict(COMMITTED), lambda rel: None)
    assert problems, "HEAD 那侧全读不出来，却报了通过"


def test_it_still_reads_the_right_repo_when_a_git_hook_dirties_the_env(tmp_path) -> None:
    """**这条判据第一次跑进 pre-commit 就栽了：单独跑绿、钩子里红。**

    git 钩子会把 `GIT_DIR` 等塞进环境，子进程继承之后会去问**那个**仓——
    `cwd=ROOT` 压不过它。仓里已经为同一件事栽过一次
    （见 test_docs_do_not_send_you_to_a_missing_script.py 的 `_CLEAN_GIT_ENV`），
    而我又栽了一次，所以这里把它钉住：**把环境弄脏，结果必须不变。**

    **真去驱动判据**，不是在这里复述一遍洗环境的技巧——那样把判据里的
    `env=` 删掉，这条还是绿的。做法是把 `GIT_DIR` 指到一个**空的**仓
    （没有 HEAD），再调判据自己那条读法：没洗环境的话，`git show` 会去问
    那个空仓，一个文件都读不出来。
    """
    import os

    from social_archive.git_env import LEAKED_BY_GIT_HOOKS, clean_git_env

    empty = tmp_path / "someone-elses-repo"
    empty.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=empty,
                   env=clean_git_env(), check=True)

    saved = {k: os.environ.get(k) for k in LEAKED_BY_GIT_HOOKS}
    try:
        os.environ["GIT_DIR"] = str(empty / ".git")
        os.environ["GIT_WORK_TREE"] = str(empty)
        # **环境是脏的，现在直接驱动判据自己那条读法。**
        # `clean_git_env()` 是函数、每次现算，所以不用重新加载模块——
        # 把判据里的 `env=` 删掉，这一条当场红。
        assert "GIT_DIR" not in clean_git_env(), "洗环境这一步自己没生效"
        got = _module._head_reader(_module._prefix())("manifest.json")
        assert got and b'"manifest_version"' in got, (
            "环境里有别的仓的 GIT_DIR 时，判据读不到 HEAD 里的 manifest.json——"
            "它会在 pre-commit 里全程空扫，而空扫恰好被它自己判成失败，"
            "于是没人知道真正的原因是环境。")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_the_git_prefix_is_computed_not_hardcoded() -> None:
    """前缀必须现算——这个仓的根在上一层，写死 `apps/…` 会全程空扫。"""
    prefix = _module._prefix()
    assert prefix.endswith("apps/browser-extension/"), prefix
    # 走判据自己那条读法（**它会洗掉钩子塞的 GIT_DIR**）。这一行原来是裸的
    # subprocess.run，于是 pre-commit 里红、单独跑绿——上一条判据钉的就是它。
    got = _module._head_reader(prefix)("manifest.json")
    assert got is not None, (
        f"用现算出来的前缀 {prefix} 读不到 HEAD 里的 manifest.json——"
        "那么这条判据在生产上会全程空扫")
    assert b'"manifest_version"' in got
