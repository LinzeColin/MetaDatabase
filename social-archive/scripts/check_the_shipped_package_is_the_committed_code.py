#!/usr/bin/env python3
"""他现在能下载到的那个包，和 HEAD 里那份代码是不是同一份（2026-08-07）。

## 为什么要有它

2026-08-07 生产上摆了大约四十分钟一个**打不开连接面板**的扩展包：
`host_permissions` 里少了 `social-archive-api.linzezhang.com`，插件够不着
后端，面板显示「读不到可连接的来源：Failed to fetch」，一颗按钮都没有——
正是 Owner 说的「点了没反应」的形状。

来路是我自己：部署在后台跑，而我在同一时间为了做反例改了 manifest。
部署第 0 步的「工作树干净」闸**在最开头就过完了**，随后 `run_all_drills`
跑五分钟，而**每个演练自己会重打一次包**——坏的那份就是这么被打出来、
同步上去的。

**而第 8 步没拦住**：它比的是「下载页下发的 zip」对「本地 dist 里的 zip」。
两个一样坏的东西比起来是一致的——这是「两个错互相抵消所以门一直是绿的」
那个形状。要比的必须是一个**它证不了自己**的东西：git 里那个提交。

## 它答的是哪一句

「**他现在点下载，拿到的是不是我提交的那份代码**」——
不是「我这台机器上的 zip 和服务器上的 zip 一样吗」。

## 边界

· 只读：一个 GET，外加 `git show`。不写、不部署、不改任何东西。
· 它不验代码对不对，只验**发出去的和入了库的是同一份**。
· 空扫要当失败：一个都没比到必须红，不许打出一个看起来是绿的 0。
  （这份判据第一版就栽在这儿：git 路径少了仓内前缀，27 个文件全被跳过，
  打出「0 个不同」——差点被读成通过。）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# **git 钩子会把这些塞进环境**，子进程继承之后会去问那个仓而不是 cwd 这个。
# 仓里已经为此栽过一次（见 test_docs_do_not_send_you_to_a_missing_script.py），
# 这条判据第一次跑进 pre-commit 就又栽了同一跤：单独跑绿、钩子里红。
# **不洗环境的话，`cwd=ROOT` 是没有用的**——GIT_DIR 压过 cwd。
_LEAKED_BY_GIT_HOOKS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                        "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")
_CLEAN_GIT_ENV = {k: v for k, v in os.environ.items() if k not in _LEAKED_BY_GIT_HOOKS}
EVIDENCE = ROOT / "evidence" / "G5" / "SHIPPED_PACKAGE_IS_THE_COMMIT.json"
URL = ("https://social-archive-api.linzezhang.com"
       "/downloads/social-archive-extension.zip")
# Cloudflare 会 403 掉 `Python-urllib`——生产可达性演练上踩过一次。
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (package-check)"}


def compare(package: dict[str, bytes], head_bytes) -> tuple[list[str], dict]:
    """**取数和判断分开**，这样能拿「篡改过的包」喂它，证明它真的会红。

    `head_bytes(rel)` 返回 HEAD 里那个文件的字节，没有就返回 None。
    """
    same: list[str] = []
    differs: list[str] = []
    not_in_commit: list[str] = []
    for rel in sorted(package):
        committed = head_bytes(rel)
        if committed is None:
            not_in_commit.append(rel)
        elif committed == package[rel]:
            same.append(rel)
        else:
            differs.append(rel)

    problems: list[str] = []
    # **空扫必须是失败。** 打出「0 个不同」看着像通过，其实是什么都没比。
    if not same and not differs:
        problems.append(
            "**一个文件都没比到**——这不是通过，是这条判据没找到对照物"
            "（git 路径前缀错了？包的结构变了？）")
    if differs:
        problems.append(
            f"**他下载到的包和 HEAD 不是同一份**：{differs[:6]}"
            f"（共 {len(differs)} 个文件不同）——"
            "生产上摆着的是一份没有对应提交的代码，出事时无从回溯")
    if not_in_commit:
        problems.append(
            f"**包里有 HEAD 里不存在的文件**：{not_in_commit[:6]}"
            f"（共 {len(not_in_commit)} 个）——它是从哪来的？")
    measured = {"files_in_package": len(package), "identical_to_head": len(same),
                "differs_from_head": len(differs), "not_in_commit": len(not_in_commit)}
    return problems, measured


def _head_reader(prefix: str):
    def read(rel: str) -> bytes | None:
        done = subprocess.run(["git", "show", f"HEAD:{prefix}{rel}"],
                              cwd=ROOT, env=_CLEAN_GIT_ENV,
                              capture_output=True, check=False)
        return done.stdout if done.returncode == 0 else None
    return read


def _prefix() -> str:
    """仓根不一定就是这个目录——**现算，别写死。**"""
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         cwd=ROOT, env=_CLEAN_GIT_ENV,
                         capture_output=True, text=True, check=True)
    inside = ROOT.relative_to(Path(top.stdout.strip())).as_posix()
    return (f"{inside}/" if inside != "." else "") + "apps/browser-extension/"


def main() -> int:
    parser = argparse.ArgumentParser(description="生产下发的包 vs HEAD（只读）")
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    try:
        with urllib.request.urlopen(
                urllib.request.Request(URL, headers=BROWSER_UA), timeout=90) as response:
            blob = response.read()
    except Exception as error:                                    # noqa: BLE001
        print(json.dumps({"status": "FAIL", "error_code": "DOWNLOAD_FAILED",
                          "message_zh": f"下载不到发布包：{error}"},
                         ensure_ascii=False, indent=2))
        return 2

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        # 包可能带一层顶层目录，也可能不带——现看，别假设。
        tops = {n.split("/", 1)[0] for n in names if "/" in n}
        strip = len(tops) == 1 and not any("/" not in n for n in names)
        package = {(n.split("/", 1)[1] if strip else n): archive.read(n) for n in names}

    problems, measured = compare(package, _head_reader(_prefix()))
    report = {
        "status": "PASS" if not problems else "FAIL",
        "downloaded_from": URL,
        "compared_against": "git HEAD:" + _prefix(),
        "measured": measured,
        "problems": problems,
        "what_this_answers_zh": (
            "他现在点下载拿到的，是不是我提交的那份代码。**不是**"
            "「我这台机器上的 zip 和服务器上的 zip 一样吗」——那两个可以一样地坏。"),
        "boundary_zh": "只读；一个 GET 加 git show；不验代码对不对，只验发出去的等于入了库的。",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    if args.brief:
        print(f"  {report['status']} · 包里 {measured['files_in_package']} 个文件，"
              f"{measured['identical_to_head']} 个与 HEAD 逐字节一致")
        for item in problems:
            print(f"    · {item}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
